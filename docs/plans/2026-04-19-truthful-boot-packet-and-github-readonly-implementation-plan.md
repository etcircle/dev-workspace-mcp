# Dev Workspace MCP Truthful Boot Packet + Read-Only GitHub Surface Implementation Plan

> **For Hermes:** execute this in a fresh session with `subagent-driven-development`. Use one implementation subagent per task group, then a separate review subagent, then a separate test/proof subagent. Parent reruns every claimed proof before accepting the wave.

**Goal:** finish the next honest product slice by fixing the still-fake boot/snapshot seams and adding the smallest useful read-only GitHub tracking surface on top of the now-landed workspace memory index.

**Architecture:** this is a two-track wave, but not a kitchen-sink rewrite. **Track A** fixes contract truthfulness: `project_snapshot` must become a compact public boot packet, and `watcher_health` / snapshot watcher state must stop pretending a real filesystem watcher exists. **Track B** adds a read-only GitHub service that resolves the repo from the project’s git remote and exposes a narrow MCP surface for repo, issue, and PR reads only. No GitHub writes, no Actions/logs yet, no new fake auth story.

**Tech Stack:** Python 3.11, FastMCP/FastAPI transport, Pydantic models, existing git/codegraph/runtime/tool registry seams, `httpx`, pytest, ruff.

---

## Why this is the right next wave

Current grounded repo state at planning time:
- date: `2026-04-19 12:38:03 BST`
- branch: `main`
- `HEAD = 5bf469a`
- branch state: `main...origin/main [ahead 2]`
- only local dirt: untracked `.hermes/`
- baseline proofs already known green in the current session:
  - `python -m pytest -q`
  - `python -m ruff check .`

What is already landed and should **not** be re-planned as future work:
- stdio + HTTP transport
- CLI parity for the core local tools
- project bootstrap + direct connections
- persistent workspace memory index (`SQLite + FTS5`) with MCP tools + CLI
- snapshot memory hints (`memory_index_status`, `recent_decision_titles`, etc.)

What is still visibly wrong or incomplete in the live repo:
1. `ProjectSnapshot` still embeds the full `ProjectRecord`, which leaks absolute paths and raw manifest/policy internals into the public boot packet.
2. watcher state is still dishonest: the manager says it tracks watcher intent only, but `watcher_health()` / snapshot flows still report `active`.
3. README/status docs are stale relative to the live repo.
4. GitHub tracking is still only stored as refs in memory records; there is still **no** read-only GitHub tool surface.

This plan intentionally **supersedes the old “Wave 4 boot packet” direction** in `docs/plans/2026-04-18-peer-review-wave-tracker.md` for the immediate next slice. Snapshot memory hints already landed; the remaining work is now a **truthfulness + GitHub-read** consolidation wave, not a greenfield boot-packet build.

---

## Explicit scope

### In scope now
1. Slim the public `project_snapshot` contract.
2. Make watcher/index status honest.
3. Refresh README/docs to match the live repo.
4. Add a read-only GitHub repo/issues/PR surface resolved from the project’s git remote.
5. Add focused tests and transport/registry expectation updates for the new public surface.

### Explicitly deferred
Do **not** smuggle these into this wave:
- GitHub write tools (`create_pr`, `comment`, `request_review`, etc.)
- GitHub Actions runs/logs tools
- durable job/log persistence across restarts
- public/remote auth for hosted HTTP
- full CLI parity for the new GitHub tools
- changing the existing `project_id` routing model
- a real filesystem watcher backend

If a child drifts into any of those, stop and cut scope back down.

---

## Canonical execution tracker

Use this tracker as the delegated execution fence for the wave:
- `docs/plans/2026-04-19-truthful-boot-packet-and-github-readonly-wave-tracker.md`

If implementation needs more files than the tracker allows, amend the tracker first.

---

## Task Group 1 — Reset the public snapshot contract

**Objective:** make `project_snapshot` a compact public boot packet instead of dumping the full internal `ProjectRecord` shape.

**Files:**
- Modify: `dev_workspace_mcp/models/projects.py`
- Modify: `dev_workspace_mcp/projects/snapshots.py`
- Test: `tests/test_project_snapshot.py`
- Test: `tests/test_transport_http.py` (only if exported shape / exposed tool expectations need updates)

**Required design decisions:**
- Replace `ProjectSnapshot.project: ProjectRecord` with a smaller public identity/header model.
- The new public snapshot header should contain only what an external coding agent actually needs at boot, for example:
  - `project_id`
  - `display_name`
  - `aliases`
  - `manifest_present`
- Do **not** expose inside the public snapshot header:
  - absolute `root_path`
  - absolute `manifest_path`
  - full raw manifest object
  - raw `ProjectPolicy`
- Keep the already-existing top-level summary fields (`services`, `policy`, `state_docs`, `stack`, `recommended_*`, etc.) as the public boot packet.

**Important rule:**
- relative paths only in the public contract
- if a path is surfaced in snapshot fields like `state_docs`, `standards_docs`, or future doc refs, it must stay repo-relative

**Required proofs:**
- snapshot no longer contains absolute `root_path` / `manifest_path` in `data.project`
- snapshot still contains the expected summarized policy/service/state-doc information
- transport tests that enumerate/serialize snapshot output still pass

**Verification commands:**
```bash
python -m pytest -q tests/test_project_snapshot.py tests/test_transport_http.py
```

---

## Task Group 2 — Make watcher/index status honest

**Objective:** stop reporting a fake active watcher when the code only has snapshot/index metadata and no real filesystem watcher backend.

**Files:**
- Modify: `dev_workspace_mcp/codegraph/models.py`
- Modify: `dev_workspace_mcp/codegraph/watcher_manager.py`
- Modify: `dev_workspace_mcp/codegraph/service.py`
- Modify: `dev_workspace_mcp/projects/snapshots.py`
- Test: `tests/test_project_snapshot.py`
- Optional if targeted proofs need it: `tests/test_codegraph_tools.py`

**Required design decisions:**
- `watcher_health()` must not mutate watcher state just because a read path was called.
- `CodegraphWatcherManager` should remain an intent/index metadata holder until a real backend exists.
- If an index snapshot exists, the response should say so honestly without claiming `active=True`.
- Prefer an honest status model like:
  - `not_configured`
  - `configured`
  - `indexed`
  - `inactive`
  rather than continuing to call it `active` when there is no live watcher backend.

**Important rule:**
- do not rename public tools in this wave
- fix the semantics under the existing `watcher_health` / snapshot watcher surface instead of inventing a whole new tool

**Required proofs:**
- configured watch paths with a built snapshot no longer claim a fake active watcher
- snapshot capability text and watcher summary remain consistent with the real backend state
- snapshot tests assert the new honest semantics

**Verification commands:**
```bash
python -m pytest -q tests/test_project_snapshot.py
```

---

## Task Group 3 — Refresh README and plan/docs truthfulness

**Objective:** make the repo docs match the live repo after the memory wave and the watcher/snapshot truthfulness reset.

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-04-18-peer-review-wave-tracker.md` (small note only, to demote the old Wave 4 direction to historical/background context)

**Required behavior:**
- remove stale claims that persistent SQLite/BM25 search is “not implemented yet”
- keep README blunt about what is still missing:
  - GitHub read-only tools are only implemented after this wave lands
  - GitHub write tools remain absent
  - no real filesystem watcher backend yet
  - durable jobs/logs still deferred
- add one short note in the older peer-review tracker making it clear the old boot-packet wave is now historical and that this newer plan is the execution artifact for the next slice

**Required proofs:**
- README examples and “not implemented yet” section match the live repo after this wave
- no stale line still claims the memory index is absent
- the older wave tracker no longer looks like the next thing to execute blindly

**Verification commands:**
```bash
python -m dev_workspace_mcp.app describe
```
plus manual doc read-through.

---

## Task Group 4 — Add GitHub repo resolution + read-only service foundation

**Objective:** add the smallest honest GitHub integration layer for repo, issue, and PR reads, scoped by `project_id` and resolved from the project’s git remote.

**Files:**
- Modify: `dev_workspace_mcp/models/errors.py`
- Modify: `dev_workspace_mcp/gittools/service.py` (only if repo-remote parsing belongs here)
- Create: `dev_workspace_mcp/models/github.py`
- Create: `dev_workspace_mcp/github_tools/__init__.py`
- Create: `dev_workspace_mcp/github_tools/service.py`
- Test: `tests/test_gittools.py`
- Create: `tests/test_github_tools.py`

**Required design decisions:**
- Resolve `owner/repo` from the project’s git `origin` remote.
- Support standard GitHub remote shapes at minimum:
  - `https://github.com/owner/repo.git`
  - `git@github.com:owner/repo.git`
- If the repo has no GitHub remote, return a structured domain error.
- Keep the new GitHub surface **read-only**.
- Prefer a small service abstraction that uses `httpx` against the GitHub REST API.
- Auth behavior must stay honest:
  - public repo reads may work unauthenticated
  - private/rate-limited flows may require `GITHUB_TOKEN`
  - if auth is required and unavailable, return a structured error instead of hand-waving

**Suggested public error codes to add:**
- `GITHUB_REMOTE_NOT_CONFIGURED`
- `GITHUB_AUTH_REQUIRED`
- `GITHUB_REQUEST_FAILED`

**Required DTOs/models:**
- repo summary / repo details response
- issue summary / issue details response
- PR summary / PR details response
- PR file list response
- search request/response shapes

**Important rule:**
- keep local git tools separate from GitHub tools
- do not smuggle GitHub writes into the first slice just because the API is right there

**Required proofs:**
- GitHub origin parsing works for HTTPS + SSH origin formats
- non-GitHub or missing origin returns structured error
- service tests cover unauthenticated/public response handling and error mapping

**Verification commands:**
```bash
python -m pytest -q tests/test_gittools.py tests/test_github_tools.py
```

---

## Task Group 5 — Wire the read-only GitHub MCP tool surface

**Objective:** expose a narrow read-only GitHub surface via MCP, with stable envelopes and transport/test coverage.

**Files:**
- Modify: `dev_workspace_mcp/runtime.py`
- Modify: `dev_workspace_mcp/mcp_server/tool_registry.py`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_transport_http.py`
- Test: `tests/test_github_tools.py`

**Frozen public tool names for this wave:**
- `github_repo`
- `github_issue_read`
- `github_issue_search`
- `github_pr_read`
- `github_pr_files`

**Not in this wave:**
- `github_actions_runs`
- `github_actions_logs`
- any write tools

**Handler rules:**
- all tools remain project-scoped through `project_id`
- tool handlers must validate input with pydantic request models
- tool handlers must map remote/auth/parse failures into structured domain errors
- transport/registry tests must be updated in the same wave; do not leave stale exported-tool expectations behind

**Required proofs:**
- tool registry exposes the new GitHub tools
- HTTP transport tool listing expectations are updated
- MCP envelopes stay stable for success + error cases

**Verification commands:**
```bash
python -m pytest -q tests/test_mcp_server.py tests/test_transport_http.py tests/test_github_tools.py
```

---

## Task Group 6 — Final proof lane and parent review prep

**Objective:** prove the whole slice as one coherent wave and leave a clean execution artifact for the parent review in the next session.

**Files:**
- No new feature files expected here unless proofs expose one tiny follow-up fix.
- If tests require narrow adjustments, keep them inside already-touched test modules only.

**Required parent proofs after delegated implementation:**
```bash
python -m ruff check .
python -m pytest -q
python -m dev_workspace_mcp.app describe
```

**Manual parent smoke expectations:**
1. `project_snapshot` returns a compact public header with no absolute path leakage
2. snapshot watcher state is honest (no fake active watcher)
3. `github_repo` works for a project whose `origin` points at GitHub
4. `github_issue_search` or `github_issue_read` works for the same repo
5. `github_pr_read` / `github_pr_files` return structured read-only results
6. a project with no GitHub remote returns a structured error, not a traceback

**Suggested manual smoke command pattern:**
```bash
python - <<'PY'
from dev_workspace_mcp.runtime import create_runtime
from dev_workspace_mcp.mcp_server.tool_registry import build_tool_registry
runtime = create_runtime()
tools = build_tool_registry(runtime.project_registry, services=runtime.services)
print(tools.run("project_snapshot", project_id="dev-workspace-mcp"))
print(tools.run("github_repo", project_id="dev-workspace-mcp"))
PY
```

---

## Subagent execution model for the next session

### Parent-owned seams to freeze first
Before delegating implementation, parent should re-read and freeze these seam files directly:
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
- GitHub error-code semantics

### Implementation agents
- **Agent A:** Task Groups 1 + 2 (snapshot contract + watcher honesty)
  - reason: these share snapshot/watcher models and should stay in one lane
- **Agent B:** Task Group 3 (README/docs truthfulness)
  - can run after the parent freezes the truthfulness language for the wave
- **Agent C:** Task Groups 4 + 5 (GitHub service + MCP tool wiring)
  - reason: service + public tool contract belong in one lane

### Review agents
After each implementation lane lands:
- **Review 1 — spec compliance:** did the child match this plan and stay inside scope?
- **Review 2 — code quality:** any contract dishonesty, brittle parsing, error-shape drift, or weak tests?

### Test/proof agent
After review passes:
- rerun the targeted pytest nodes for that lane
- rerun transport/registry proofs if public tools changed
- perform one small manual smoke path for the lane

### Parent review
At the end, parent must:
1. inspect the touched files directly
2. rerun targeted tests
3. rerun `python -m pytest -q`
4. rerun `python -m ruff check .`
5. run the manual smoke commands
6. record PASS / REQUEST_CHANGES against the tracker

No exceptions.

---

## Final acceptance criteria

This wave is complete only if all of these are true:
- `project_snapshot` no longer leaks absolute/internal `ProjectRecord` details
- watcher state is honest and no longer reports a fake active backend
- README/docs match the live repo state after the wave
- GitHub repo resolution from project remote works
- read-only GitHub tools exist for repo/issues/PRs
- transport/registry tests were updated in the same wave
- `python -m pytest -q` passes
- `python -m ruff check .` passes
- parent manual smoke passes

If any of that is false, the wave is still half-baked.
