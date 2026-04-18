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

    bootstrap = subparsers.add_parser("bootstrap", help="Bootstrap project helpers.")
    bootstrap_subparsers = bootstrap.add_subparsers(dest="bootstrap_command", required=True)
    bootstrap_create = bootstrap_subparsers.add_parser(
        "create",
        help="Create a new project inside the workspace roots.",
    )
    bootstrap_create.add_argument("folder_name")
    _add_bootstrap_common_arguments(bootstrap_create)
    bootstrap_create.add_argument(
        "--git-init",
        action="store_true",
        help="Initialize a git repository after creating the project folder.",
    )
    bootstrap_clone = bootstrap_subparsers.add_parser(
        "clone",
        help="Clone a repository into the workspace roots.",
    )
    bootstrap_clone.add_argument("repo_url")
    _add_bootstrap_common_arguments(bootstrap_clone)
    bootstrap_clone.add_argument("--branch", help="Clone and checkout one branch.")
    bootstrap_import = bootstrap_subparsers.add_parser(
        "import",
        help="Import an existing project path under the workspace roots.",
    )
    bootstrap_import.add_argument("path")
    _add_bootstrap_common_arguments(bootstrap_import)

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

    connections = subparsers.add_parser("connections", help="Tracked connection helpers.")
    connections_subparsers = connections.add_subparsers(
        dest="connections_command",
        required=True,
    )
    connections_list = connections_subparsers.add_parser(
        "list",
        help="List tracked connections for one project.",
    )
    connections_list.add_argument("project_id")
    connections_configure = connections_subparsers.add_parser(
        "configure",
        help="Create or update one tracked direct connection profile.",
    )
    connections_configure.add_argument("project_id")
    connections_configure.add_argument("connection_name")
    connections_configure.add_argument("--kind", required=True)
    connections_configure.add_argument("--host-env", required=True)
    connections_configure.add_argument("--port-env", required=True)
    connections_configure.add_argument("--database-env")
    connections_configure.add_argument("--user-env")
    connections_configure.add_argument("--password-env")
    connections_configure.add_argument("--token-env")
    connections_configure.add_argument("--ssl-mode-env")
    connections_configure.add_argument("--timeout-sec", type=int)
    connections_configure.add_argument(
        "--env",
        action="append",
        default=[],
        type=_parse_env_assignment,
        metavar="KEY=VALUE",
        help="Repeat to write local-only values into .devworkspace/agent.env.",
    )
    connections_test = connections_subparsers.add_parser(
        "test",
        help="Run the direct TCP smoke test for one tracked connection.",
    )
    connections_test.add_argument("project_id")
    connections_test.add_argument("connection_name")

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
    parsed_argv = list(argv) if argv is not None else None
    if _is_run_command(parsed_argv):
        args = _parse_run_command(parser, parsed_argv or [])
    else:
        args = parser.parse_args(parsed_argv)
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

    if args.command == "bootstrap":
        return _run_bootstrap_command(tools, args)

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

    if args.command == "connections":
        return _run_connections_command(tools, args)

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


def _add_bootstrap_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id")
    parser.add_argument("--display-name")


def _run_bootstrap_command(tools: ToolRegistry, args: argparse.Namespace) -> dict[str, Any]:
    if args.bootstrap_command == "create":
        return tools.run(
            "bootstrap_project",
            mode="create",
            folder_name=args.folder_name,
            project_id=args.project_id,
            display_name=args.display_name,
            git_init=args.git_init,
        )

    if args.bootstrap_command == "clone":
        return tools.run(
            "bootstrap_project",
            mode="clone",
            repo_url=args.repo_url,
            branch=args.branch,
            project_id=args.project_id,
            display_name=args.display_name,
        )

    return tools.run(
        "bootstrap_project",
        mode="import",
        path=args.path,
        project_id=args.project_id,
        display_name=args.display_name,
    )


def _is_run_command(argv: list[str] | None) -> bool:
    tokens = list(argv or [])
    while tokens[:1] == ["--json"]:
        tokens = tokens[1:]
    return tokens[:1] == ["run"]


def _parse_run_command(
    parser: argparse.ArgumentParser,
    argv: list[str],
) -> argparse.Namespace:
    tokens = list(argv)
    pretty = False
    while tokens[:1] == ["--json"]:
        pretty = True
        tokens = tokens[1:]
    if not tokens or tokens[0] != "run":
        parser.error("Unsupported CLI command: run")
    run_tokens = tokens[1:]
    if not run_tokens:
        parser.error("run requires a project_id.")

    project_id = run_tokens[0]
    cwd: str | None = None
    timeout_sec: int | None = None
    background = False
    preset: str | None = None
    argv_tokens: list[str] = []
    index = 1
    while index < len(run_tokens):
        token = run_tokens[index]
        if token == "--":
            argv_tokens = run_tokens[index + 1 :]
            break
        if argv_tokens:
            argv_tokens.append(token)
            index += 1
            continue
        if token == "--background":
            background = True
            index += 1
            continue
        if token in {"--cwd", "--timeout-sec", "--preset"}:
            if index + 1 >= len(run_tokens):
                parser.error(f"{token} requires a value.")
            value = run_tokens[index + 1]
            if token == "--cwd":
                cwd = value
            elif token == "--timeout-sec":
                try:
                    timeout_sec = int(value)
                except ValueError:
                    parser.error("--timeout-sec requires an integer value.")
            else:
                preset = value
            index += 2
            continue
        argv_tokens = run_tokens[index:]
        break
    argv_tokens = _normalize_argv(argv_tokens)
    if not argv_tokens:
        parser.error("run requires a command argv.")
    return argparse.Namespace(
        json=pretty,
        command="run",
        project_id=project_id,
        cwd=cwd,
        timeout_sec=timeout_sec,
        background=background,
        preset=preset,
        argv=argv_tokens,
    )


def _run_connections_command(tools: ToolRegistry, args: argparse.Namespace) -> dict[str, Any]:
    if args.connections_command == "list":
        return tools.run("list_connections", project_id=args.project_id)

    if args.connections_command == "configure":
        return tools.run(
            "configure_connection",
            project_id=args.project_id,
            connection_name=args.connection_name,
            profile=_connection_profile_from_args(args),
            env_updates=dict(args.env),
        )

    return tools.run(
        "test_connection",
        project_id=args.project_id,
        connection_name=args.connection_name,
    )


def _connection_profile_from_args(args: argparse.Namespace) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "kind": args.kind,
        "host_env": args.host_env,
        "port_env": args.port_env,
    }
    optional_env_fields = {
        "database_env": args.database_env,
        "user_env": args.user_env,
        "password_env": args.password_env,
        "token_env": args.token_env,
        "ssl_mode_env": args.ssl_mode_env,
    }
    profile.update({key: value for key, value in optional_env_fields.items() if value is not None})
    if args.timeout_sec is not None:
        profile["test"] = {"timeout_sec": args.timeout_sec}
    return profile


def _parse_env_assignment(value: str) -> tuple[str, str]:
    key, separator, env_value = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("Expected env assignment in KEY=VALUE form.")
    if not key:
        raise argparse.ArgumentTypeError("Env assignment key must not be empty.")
    return key, env_value


def _normalize_argv(argv: list[str]) -> list[str]:
    if argv[:1] == ["--"]:
        return argv[1:]
    return argv


__all__ = ["build_parser", "main"]
