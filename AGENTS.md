# Dev Workspace MCP - Working Guide

## Mission

Build a project-aware MCP server that gives external coding agents a clean, structured interface for understanding code, editing files, running bounded commands, inspecting services and logs, and maintaining repo-local task state.

## Non-negotiables

- Public tools use the new contract only.
- `project_id` is the universal routing key for all project-scoped tools.
- Relative paths only in the public contract.
- CodeGraph remains an internal subsystem, not the public API boundary.
- Services are first-class and distinct from bounded jobs.
- State docs live in `.devworkspace/` and enforce size limits.
- Prefer `argv[]` command execution over raw shell strings.

## Initial package layout

- `dev_workspace_mcp/mcp_server/` - tool registry, HTTP transport, result envelope
- `dev_workspace_mcp/projects/` - project discovery, registry, manifest, snapshots
- `dev_workspace_mcp/codegraph/` - semantic adapters and watcher/index management
- `dev_workspace_mcp/files/` - project-relative file operations and patching
- `dev_workspace_mcp/commands/` - bounded commands and jobs
- `dev_workspace_mcp/services/` - lifecycle, logs, health
- `dev_workspace_mcp/state_docs/` - memory/roadmap/tasks state docs
- `dev_workspace_mcp/gittools/` - structured git helpers
- `dev_workspace_mcp/http_tools/` - local HTTP verification
- `dev_workspace_mcp/probes/` - named diagnostics

## Coding rules

- Keep models transport-agnostic where possible.
- Centralize domain errors and stable error codes.
- Make partial degradation explicit with warnings, not silent failures.
- Avoid fake abstractions. Thin, boring modules beat clever nonsense.
- Stub cleanly now; fill behavior iteratively.

## Definition of done for scaffold stage

- Editable install works.
- Package imports succeed.
- Core directories and module files exist.
- There is a runnable entrypoint.
- There is a minimal test suite covering import/bootstrap shape.
