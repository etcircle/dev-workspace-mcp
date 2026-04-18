# Project Bootstrap + Connections Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to execute this plan task-by-task. One implementation subagent per task, then a spec-review subagent, then a quality/test-review subagent. Parent reruns the proof commands and records the verdict before moving on.

**Goal:** Add a first-class project onboarding flow to `dev-workspace-mcp` so an agent can create, clone, or import a project into a workspace root, assign a canonical `project_id`, scaffold repo-local state files, configure tracked direct connection profiles, optionally write local-only env values, and run an honest connection smoke test.

**Architecture:** Keep this inside the existing product boundary. Project bootstrap and connection management belong to the project/runtime/tooling layer — not to raw shell commands and not to a separate web app. The immediate slice should stay local-first and honest: direct connections only, TCP-level `test_connection`, local-only `.devworkspace/agent.env` for secrets, and no SSH tunnel lifecycle yet.

**Tech Stack:** Python 3.11, Pydantic v2, PyYAML, stdlib `socket`, existing `argparse` CLI, existing MCP tool registry/runtime.

---

## Grounded live-repo facts

Verified against the current repo before writing this plan:
- project discovery already exists via `dev_workspace_mcp/projects/discovery.py`
- project records come from `.git` or `.devworkspace.yaml`, and canonical `project_id` comes from manifest or folder name via `dev_workspace_mcp/projects/registry.py`
- there is no project bootstrap/import tool yet
- there is no connection-profile model/service yet
- current CLI only exposes `projects`, `snapshot`, `read`, `run`, `git status`, and `memory` helpers (`dev_workspace_mcp/cli/main.py`)
- the tool registry has no onboarding/connection tools yet (`dev_workspace_mcp/mcp_server/tool_registry.py`)
- current tests already cover registry, CLI parity, and tool registry shape (`tests/test_projects.py`, `tests/test_cli.py`, `tests/test_mcp_server.py`)
- current root verification entrypoints are real and should stay canonical:
  - `python -m pytest -q`
  - `python -m ruff check .`
  - `python -m dev_workspace_mcp.app describe`
  - `python -m dev_workspace_mcp.app cli projects`

## Scope

### In scope for this execution plan
1. `bootstrap_project` tool + CLI support for:
   - `create`
   - `clone`
   - `import`
2. canonical `project_id` persistence into `.devworkspace.yaml`
3. default scaffolding for:
   - `.devworkspace/memory.md`
   - `.devworkspace/tasks.md`
   - `.devworkspace/roadmap.md`
   - `.devworkspace/policy.yaml`
4. tracked direct connection profiles stored in `.devworkspace.yaml`
5. local-only `.devworkspace/agent.env` support for env values written by the agent
6. `list_connections`, `configure_connection`, and `test_connection`
7. honest connection testing via direct TCP connectivity only
8. CLI parity, MCP tool exposure, README truthfulness, and tests

### Explicitly out of scope for this wave
- web UI
- SSH tunnel lifecycle (`open_tunnel` / `close_tunnel`)
- database-specific query tools
- driver-specific auth/login verification
- background tunnel management
- remote secret managers

Blunt rule: do **not** pretend SSH is implemented in this wave. That is later.

---

## Contract decisions to freeze before delegation

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
- repeated optional env writes use `--env KEY=VALUE`

### `project_id` and display-name rules
- if bootstrap receives `--project-id`, use it as-is after the existing repo validation rules
- otherwise derive `project_id` from the target folder name using the **same shared helper/logic** that registry resolution uses in this wave
- do **not** invent a bootstrap-only slugification rule
- CLI `--display-name` writes manifest field `name`; do **not** add a separate manifest `display_name` field

### Response fields to keep stable in this wave
- `bootstrap_project` should return at least:
  - `project_id`
  - `root_path`
  - `manifest_path`
  - `created_files`
  - `git_initialized`
  - `git_cloned`
  - `warnings`
  - `recommended_next_tools`
- `test_connection` should return at least:
  - `connection_name`
  - `kind`
  - `transport`
  - `host`
  - `port`
  - `reachable`
  - `message`

### Manifest shape
Tracked config stays in `.devworkspace.yaml`.

Example target shape:

```yaml
name: Demo Project
project_id: demo-project
aliases: []
codegraph:
  watch_paths: []
connections:
  primary:
    kind: postgres
    transport: direct
    host_env: PGHOST
    port_env: PGPORT
    database_env: PGDATABASE
    user_env: PGUSER
    password_env: PGPASSWORD
    test:
      type: tcp
      timeout_sec: 3
```

### Secret handling
- local-only file: `.devworkspace/agent.env`
- tracked config stores env variable **names**, not secret values
- if `configure_connection` receives `env_updates`, it writes/updates `.devworkspace/agent.env`
- bootstrap must ensure target repo `.gitignore` contains `.devworkspace/agent.env`

### Connection honesty
- immediate wave supports `transport: direct`
- `test_connection` proves only:
  - required env values resolve
  - host/port parse cleanly
  - TCP socket connect succeeds/fails honestly
- it does **not** prove DB auth, schema validity, or query success
- `test_connection` must obey the same hostname policy semantics as the repo's local HTTP verifier:
  - localhost allowed only when project policy allows it
  - non-local hosts must respect `.devworkspace/policy.yaml`
  - do **not** add an ad hoc network-policy bypass

---

## Execution protocol for the next session

### Session-open sequence
1. Read:
   - `docs/plans/2026-04-18-project-onboarding-and-db-connections.md`
   - `docs/plans/2026-04-18-project-bootstrap-and-connections-implementation-plan.md`
2. Reconfirm repo state:
   - `git status --short --branch`
   - `python -m pytest -q`
3. Parent freezes the contract seam below in a tiny parent-owned pass before delegating implementation.

### Parent-owned seam
Parent should lock these files/contracts first, then delegate leaf work:
- `dev_workspace_mcp/models/errors.py`
- `dev_workspace_mcp/models/projects.py`
- `dev_workspace_mcp/models/project_bootstrap.py` *(new)*
- `dev_workspace_mcp/models/connections.py` *(new)*
- final tool/CLI names listed above

Reason: these are the contract-defining files. Do not let multiple children invent competing shapes.

Practical rule: **Task 1 is parent-owned.** Delegated implementation starts at Task 2 unless the parent explicitly decides otherwise after freezing these files.

### Delegation rule
Do **not** parallelize tasks that touch the same files. This lane is sequential because bootstrap, connections, runtime wiring, and CLI parity overlap heavily.

For each task:
1. implementation subagent
2. spec-review subagent
3. quality/test-review subagent
4. parent reruns the exact proof commands
5. parent records PASS / REQUEST_CHANGES before moving on

---

## Task 1: Freeze bootstrap and connection models

**Objective:** Lock the request/response/config contract before any service or tool wiring.

**Ownership:** Parent-owned seam. Do not delegate this task until the parent has frozen the contract files.

**Files:**
- Create: `dev_workspace_mcp/models/project_bootstrap.py`
- Create: `dev_workspace_mcp/models/connections.py`
- Modify: `dev_workspace_mcp/models/projects.py`
- Modify: `dev_workspace_mcp/models/errors.py`
- Test: `tests/test_project_bootstrap.py`
- Test: `tests/test_connections.py`

**Implementation details:**
- Add bootstrap request/response models covering `create`, `clone`, and `import`
- Add connection-profile models with explicit direct-only transport
- Extend `ProjectManifest` to include `connections`
- Add any new error codes needed for bootstrap/connection flows, e.g.:
  - `BOOTSTRAP_FAILED`
  - `CONNECTION_NOT_FOUND`
  - `CONNECTION_TEST_FAILED`
  - `ENV_FILE_INVALID`
- Keep the models transport-agnostic

**Step 1: Write failing tests**
- manifest validation round-trip for `connections`
- invalid transport or missing required env refs fails validation
- bootstrap request validation covers mode-specific required fields

**Step 2: Run narrow tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py
```

Expected: FAIL because the new models do not exist yet.

**Step 3: Implement the minimal model layer**
- add the new model files
- import them into `models/projects.py` where manifest needs them
- keep defaults boring and explicit

**Step 4: Re-run narrow tests**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/models/project_bootstrap.py dev_workspace_mcp/models/connections.py dev_workspace_mcp/models/projects.py dev_workspace_mcp/models/errors.py tests/test_project_bootstrap.py tests/test_connections.py
git commit -m "feat: add bootstrap and connection contract models"
```

---

## Task 2: Add manifest-write and local env-file helpers

**Objective:** Give the repo a single honest way to persist tracked project config and local-only env values.

**Files:**
- Modify: `dev_workspace_mcp/projects/manifest.py`
- Create: `dev_workspace_mcp/shared/env_files.py`
- Test: `tests/test_project_bootstrap.py`
- Test: `tests/test_connections.py`

**Implementation details:**
- Add manifest write/update helpers to persist `.devworkspace.yaml`
- Add a tiny parser/writer for `.devworkspace/agent.env`
- Keep `.devworkspace/agent.env` simple `KEY=VALUE`, no shell export parsing nonsense
- If the env file is malformed, fail clearly with `ENV_FILE_INVALID`
- Add a helper that ensures `.gitignore` contains `.devworkspace/agent.env` exactly once

**Step 1: Write failing tests**
- writing a manifest round-trips `connections`
- env helper writes/updates keys without duplicating lines forever
- `.gitignore` helper is idempotent

**Step 2: Run narrow tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py
```

Expected: FAIL on missing helpers.

**Step 3: Implement minimal persistence helpers**
- no new dependency for dotenv handling
- keep file writes atomic enough for this local-first wave

**Step 4: Re-run narrow tests**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/projects/manifest.py dev_workspace_mcp/shared/env_files.py tests/test_project_bootstrap.py tests/test_connections.py
git commit -m "feat: add manifest and local env persistence helpers"
```

---

## Task 3: Implement project bootstrap service

**Objective:** Create, clone, or import a project and make it discoverable immediately.

**Files:**
- Create: `dev_workspace_mcp/projects/bootstrap.py`
- Modify: `dev_workspace_mcp/projects/registry.py` *(only if a tiny shared validation/helper seam is truly required; otherwise leave it alone)*
- Modify: `dev_workspace_mcp/config.py` *(only if a small helper/default is needed; do not widen scope)*
- Test: `tests/test_project_bootstrap.py`
- Test: `tests/test_projects.py`

**Implementation details:**
- `create` mode:
  - create folder under an allowed workspace root
  - optionally `git init`
  - scaffold `.devworkspace.yaml`
  - scaffold `.devworkspace/memory.md`, `tasks.md`, `roadmap.md`, `policy.yaml`
  - ensure `.gitignore` contains `.devworkspace/agent.env`
- `clone` mode:
  - run `git clone` into a workspace root
  - optionally checkout a branch
  - scaffold manifest/state docs only if missing
- `import` mode:
  - validate the target path exists
  - reject paths outside configured workspace roots unless the implementation adds an explicit import allowance and tests it
  - scaffold manifest/state docs only if missing
- refresh the project registry after mutation so the new project appears immediately in `list_projects`

**Step 1: Write failing tests**
- create mode yields a discovered project with canonical `project_id`
- import mode leaves existing files alone and adds missing `.devworkspace` files
- clone mode creates a working project from a local test repo fixture
- duplicate/invalid `project_id` fails cleanly

**Step 2: Run targeted tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_projects.py
```

Expected: FAIL because the service does not exist yet.

**Step 3: Implement minimal bootstrap service**
- prefer explicit helpers over cramming logic into the registry
- keep clone path bounded to `git`, not GitHub API nonsense
- do not silently overwrite existing manifest values

**Step 4: Re-run targeted tests**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_projects.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/projects/bootstrap.py tests/test_project_bootstrap.py tests/test_projects.py
git commit -m "feat: add project bootstrap service"
```

If `registry.py` or `config.py` were genuinely touched, add them explicitly to the commit instead of pretending they were mandatory.

---

## Task 4: Implement direct connection-profile service

**Objective:** Store safe connection metadata, optionally write local env values, and run an honest direct TCP smoke test.

**Files:**
- Create: `dev_workspace_mcp/projects/connections.py`
- Modify: `dev_workspace_mcp/projects/manifest.py`
- Modify: `dev_workspace_mcp/shared/security.py` *(only if redaction coverage for env-text/logs needs a small extension)*
- Test: `tests/test_connections.py`
- Test: `tests/test_commands.py` *(only if helper reuse touches output redaction; otherwise skip)*

**Implementation details:**
- `list_connections(project_id)` returns safe metadata only
- `configure_connection(...)` updates tracked manifest config and optionally writes `.devworkspace/agent.env`
- `test_connection(...)`:
  - loads env from process env + `.devworkspace/agent.env`
  - resolves host/port from env var names in the profile
  - validates host and integer port
  - enforces the same network-policy semantics used for local HTTP verification
  - attempts `socket.create_connection((host, port), timeout=...)`
  - returns structured success/failure details without leaking secrets
- if required env keys are missing, fail explicitly

**Step 1: Write failing tests**
- configure/list round-trip works
- env values go to `.devworkspace/agent.env`, not tracked manifest values
- `test_connection` fails cleanly for missing env vars
- `test_connection` succeeds against a local ephemeral TCP server fixture

**Step 2: Run targeted tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_connections.py
```

Expected: FAIL because the service does not exist yet.

**Step 3: Implement minimal connection service**
- direct transport only
- no DB-driver imports
- no SSH tunnel hacks

**Step 4: Re-run targeted tests**

Run:
```bash
python -m pytest -q tests/test_connections.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/projects/connections.py dev_workspace_mcp/projects/manifest.py tests/test_connections.py
git commit -m "feat: add direct connection profile service"
```

Only add `shared/security.py` or `tests/test_commands.py` if the implementation actually had to touch them.

---

## Task 5: Wire runtime and MCP tools

**Objective:** Expose bootstrap and connection flows through the real runtime/tool registry.

**Files:**
- Modify: `dev_workspace_mcp/runtime.py`
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Modify: `dev_workspace_mcp/mcp_server/server.py` *(only if needed for service plumbing; avoid scope creep)*
- Test: `tests/test_mcp_server.py`

**Implementation details:**
- add bootstrap/connection services to `RuntimeServices`
- register:
  - `bootstrap_project`
  - `list_connections`
  - `configure_connection`
  - `test_connection`
- keep result envelopes and error wrapping consistent with current tools
- update `tests/test_mcp_server.py` expected tool-name list exactly once
- remember that `tests/test_mcp_server.py` compares the exact sorted tool-name list

**Step 1: Write failing tests**
- tool registry exposes the new tool names
- tools return structured success/error envelopes

**Step 2: Run targeted tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_mcp_server.py
```

Expected: FAIL on missing tool names/service wiring.

**Step 3: Implement minimal runtime/tool wiring**
- do not widen runtime abstractions beyond what the repo already uses

**Step 4: Re-run targeted tests**

Run:
```bash
python -m pytest -q tests/test_mcp_server.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/runtime.py dev_workspace_mcp/mcp_server/tool_registry.py tests/test_mcp_server.py
git commit -m "feat: expose bootstrap and connection MCP tools"
```

Only add `mcp_server/server.py` if it was actually required.

---

## Task 6: Add CLI parity

**Objective:** Make the in-process CLI expose the same onboarding/connection flows honestly.

**Files:**
- Modify: `dev_workspace_mcp/cli/main.py`
- Test: `tests/test_cli.py`

**Implementation details:**
- add `bootstrap` subcommands:
  - `create`
  - `clone`
  - `import`
- add `connections` subcommands:
  - `list`
  - `configure`
  - `test`
- keep JSON envelope parity with the tool registry
- avoid adding a separate CLI codepath that bypasses the shared runtime/tool layer

**Step 1: Write failing tests**
- bootstrap CLI JSON output matches tool registry output
- connections CLI JSON output matches tool registry output
- one temp-workspace bootstrap flow becomes discoverable via `projects`

**Step 2: Run targeted tests to verify failure**

Run:
```bash
python -m pytest -q tests/test_cli.py
```

Expected: FAIL because the subcommands do not exist yet.

**Step 3: Implement minimal CLI wiring**
- keep argument shapes boring and explicit
- prefer flags for env refs, e.g. `--host-env PGHOST`

**Step 4: Re-run targeted tests**

Run:
```bash
python -m pytest -q tests/test_cli.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add dev_workspace_mcp/cli/main.py tests/test_cli.py
git commit -m "feat: add bootstrap and connection CLI commands"
```

---

## Task 7: README truthfulness and final proofs

**Objective:** Document only what now actually exists, then prove it end-to-end.

**Files:**
- Modify: `README.md`
- Test/Verify: existing test files above

**Implementation details:**
- document the new tool names and CLI commands
- add a manifest example with `connections`
- state bluntly that this wave supports direct TCP smoke tests, not SSH tunnel lifecycle

**Step 1: Update docs after code is real**
- no aspirational README bullshit

**Step 2: Run targeted proofs**

Run:
```bash
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py tests/test_projects.py tests/test_mcp_server.py tests/test_cli.py
python -m ruff check dev_workspace_mcp/models/project_bootstrap.py dev_workspace_mcp/models/connections.py dev_workspace_mcp/models/projects.py dev_workspace_mcp/projects/bootstrap.py dev_workspace_mcp/projects/connections.py dev_workspace_mcp/projects/manifest.py dev_workspace_mcp/shared/env_files.py dev_workspace_mcp/runtime.py dev_workspace_mcp/mcp_server/tool_registry.py dev_workspace_mcp/cli/main.py tests/test_project_bootstrap.py tests/test_connections.py tests/test_projects.py tests/test_mcp_server.py tests/test_cli.py
```

Expected: PASS

**Step 3: Run full repo proofs**

Run:
```bash
python -m pytest -q
python -m dev_workspace_mcp.app describe
python -m dev_workspace_mcp.app cli projects
```

Expected: PASS

**Step 4: Parent smoke-test the real onboarding lane**

Use a temporary workspace root so the proof does not pollute `~/dev-workspaces`.

Example proof shape:
```bash
TMP_ROOT=$(mktemp -d)
export DEV_WORKSPACE_MCP_WORKSPACE_ROOTS='["'"$TMP_ROOT"'"]'
python -m dev_workspace_mcp.app cli --json bootstrap create demo-folder --project-id demo-id --display-name "Demo Project"
python -m dev_workspace_mcp.app cli --json projects --include-paths
python -m dev_workspace_mcp.app cli --json connections configure demo-id primary --kind postgres --host-env PGHOST --port-env PGPORT --database-env PGDATABASE --user-env PGUSER --password-env PGPASSWORD
python -m dev_workspace_mcp.app cli --json connections list demo-id
```

For a real `test_connection` smoke, start a tiny local TCP listener first, then write matching env values into the temp project and run the test:
```bash
PORT=$(python - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)
python - "$PORT" <<'PY' &
import socket, sys
port = int(sys.argv[1])
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port))
s.listen(1)
conn, _ = s.accept()
conn.close()
s.close()
PY
sleep 0.2
python -m dev_workspace_mcp.app cli --json connections configure demo-id primary --kind postgres --host-env PGHOST --port-env PGPORT --database-env PGDATABASE --user-env PGUSER --password-env PGPASSWORD --env PGHOST=127.0.0.1 --env PGPORT=$PORT
python -m dev_workspace_mcp.app cli --json connections test demo-id primary
```

Also verify the temp project really contains:
- `.devworkspace.yaml`
- `.devworkspace/agent.env` *(if env updates were used)*
- `.gitignore` with `.devworkspace/agent.env`

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document bootstrap and connection flows"
```

---

## Review checklist for subagent reviewers

### Spec-review subagent must check
- no SSH tunnel lifecycle snuck into this wave
- no web UI snuck into this wave
- tracked manifest stores env variable names, not secret values
- bootstrap supports create/clone/import
- registry refresh makes new projects immediately discoverable
- CLI/tool names exactly match the frozen contract

### Quality/test-review subagent must check
- no duplicate manifest write logic in multiple modules
- no secret leakage in result payloads, logs, or README examples
- `.gitignore` handling is idempotent
- `test_connection` is honest about what it proves
- tests cover at least one negative path per major tool
- targeted proofs and full-suite proofs both exist

---

## Final parent verification standard

Do **not** finish on child summaries alone.

Parent must personally rerun:
```bash
git status --short
python -m ruff check .
python -m pytest -q tests/test_project_bootstrap.py tests/test_connections.py tests/test_projects.py tests/test_mcp_server.py tests/test_cli.py
python -m pytest -q
python -m dev_workspace_mcp.app describe
python -m dev_workspace_mcp.app cli projects
```

And parent must do the temp-workspace smoke flow from Task 7.

Verdict options:
- `PASS`
- `REQUEST_CHANGES`
- `PARTIAL PASS` *(only if targeted proofs pass but broader unrelated failures are clearly out of scope — explain them explicitly)*

---

## Deferred next wave, if this lands cleanly

Only after this plan is green:
1. add SSH tunnel transport and lifecycle management
2. add richer per-backend connection tests
3. consider a thin local web UI over the same runtime layer
4. only later consider DB-specific query helpers

That sequence matters. If you skip bootstrap and honest connection profiles first, the rest turns into shell-wrapper spaghetti.
