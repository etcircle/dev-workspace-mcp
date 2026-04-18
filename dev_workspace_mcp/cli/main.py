from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dev_workspace_mcp.cli.json_output import write_json
from dev_workspace_mcp.config import get_settings
from dev_workspace_mcp.mcp_server.tool_registry import ToolRegistry, build_tool_registry
from dev_workspace_mcp.runtime import create_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-workspace-mcp cli")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Pretty-print the stable JSON result envelope.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    projects = subparsers.add_parser("projects", help="List known projects.")
    projects.add_argument("--query", help="Filter projects by id, name, or alias.")
    projects.add_argument(
        "--include-paths",
        action="store_true",
        help="Include absolute root paths in the result.",
    )

    snapshot = subparsers.add_parser("snapshot", help="Read the project snapshot.")
    snapshot.add_argument("project_id")

    read = subparsers.add_parser("read", help="Read a project-relative file.")
    read.add_argument("project_id")
    read.add_argument("path")
    read.add_argument("--offset", type=int, default=1)
    read.add_argument("--limit", type=int)

    run = subparsers.add_parser("run", help="Run a bounded command in-process.")
    run.add_argument("project_id")
    run.add_argument("--cwd")
    run.add_argument("--timeout-sec", type=int)
    run.add_argument("--background", action="store_true")
    run.add_argument("--preset")
    run.add_argument("argv", nargs=argparse.REMAINDER)

    git = subparsers.add_parser("git", help="Git helpers.")
    git_subparsers = git.add_subparsers(dest="git_command", required=True)
    git_status = git_subparsers.add_parser("status", help="Read structured git status.")
    git_status.add_argument("project_id")
    git_status.add_argument(
        "--no-untracked",
        action="store_true",
        help="Hide untracked files from the status result.",
    )

    memory = subparsers.add_parser("memory", help="Memory state-document helpers.")
    memory_subparsers = memory.add_subparsers(dest="memory_command", required=True)
    memory_read = memory_subparsers.add_parser("read", help="Read .devworkspace/memory.md.")
    memory_read.add_argument("project_id")
    memory_patch = memory_subparsers.add_parser("patch", help="Patch memory headings.")
    memory_patch.add_argument("project_id")
    memory_patch.add_argument(
        "--section",
        action="append",
        nargs=2,
        metavar=("HEADING", "TEXT"),
        default=[],
        help="Repeat to patch one or more headings.",
    )
    memory_patch.add_argument(
        "--no-create-missing-sections",
        action="store_true",
        help="Fail instead of creating missing headings.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    tools = _build_tools()
    result = _run_cli_command(parser, tools, args)
    write_json(result, pretty=args.json)
    return 0 if result.get("ok") else 1


def _build_tools() -> ToolRegistry:
    runtime = create_runtime(get_settings())
    return build_tool_registry(runtime.project_registry, services=runtime.services)


def _run_cli_command(
    parser: argparse.ArgumentParser,
    tools: ToolRegistry,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if args.command == "projects":
        return tools.run(
            "list_projects",
            query=args.query,
            include_paths=args.include_paths,
        )

    if args.command == "snapshot":
        return tools.run("project_snapshot", project_id=args.project_id)

    if args.command == "read":
        return tools.run(
            "read_file",
            project_id=args.project_id,
            path=args.path,
            offset=args.offset,
            limit=args.limit,
        )

    if args.command == "run":
        return tools.run(
            "run_command",
            project_id=args.project_id,
            argv=_normalize_argv(args.argv),
            cwd=args.cwd,
            timeout_sec=args.timeout_sec,
            background=args.background,
            preset=args.preset,
        )

    if args.command == "git" and args.git_command == "status":
        return tools.run(
            "git_status",
            project_id=args.project_id,
            include_untracked=not args.no_untracked,
        )

    if args.command == "memory" and args.memory_command == "read":
        return tools.run("read_state_doc", project_id=args.project_id, kind="memory")

    if args.command == "memory" and args.memory_command == "patch":
        return tools.run(
            "patch_state_doc",
            project_id=args.project_id,
            kind="memory",
            section_updates={heading: text for heading, text in args.section},
            create_missing_sections=not args.no_create_missing_sections,
        )

    parser.error(f"Unsupported CLI command: {args.command}")


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv[:1] == ["--"]:
        return argv[1:]
    return argv


__all__ = ["build_parser", "main"]
