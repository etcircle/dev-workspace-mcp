from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from dev_workspace_mcp.cli.main import main as cli_main
from dev_workspace_mcp.mcp_server.server import create_server
from dev_workspace_mcp.mcp_server.transport_http import run_http_transport_async
from dev_workspace_mcp.mcp_server.transport_stdio import run_stdio_transport_async


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-workspace-mcp")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("describe", help="Print a local summary of the MCP server and tools.")

    serve = subparsers.add_parser(
        "serve-http",
        help="Run the native Streamable HTTP MCP transport.",
    )
    serve.add_argument("--host", help="Bind host override.")
    serve.add_argument("--port", type=int, help="Bind port override.")
    serve.add_argument("--path", default="/mcp", help="HTTP path for the MCP endpoint.")
    serve.add_argument("--log-level", default="info", help="Uvicorn log level.")

    subparsers.add_parser("stdio", help="Run the native stdio MCP transport.")

    cli = subparsers.add_parser("cli", help="Run the in-process JSON-first CLI.")
    cli.add_argument("cli_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    argv_list = list(argv) if argv is not None else list(sys.argv[1:])
    if argv_list and argv_list[0] == "cli":
        exit_code = cli_main(argv_list[1:])
        if exit_code:
            raise SystemExit(exit_code)
        return

    parser = build_parser()
    args = parser.parse_args(argv_list)

    if args.command == "cli":
        exit_code = cli_main(args.cli_args)
        if exit_code:
            raise SystemExit(exit_code)
        return

    server = create_server()

    if args.command in {None, "describe"}:
        _describe_server(server)
        return

    if args.command == "serve-http":
        settings = server.project_registry.settings
        host = args.host or settings.host
        port = args.port or settings.port
        print(f"Serving {server.name} on http://{host}:{port}{args.path}")
        asyncio.run(
            run_http_transport_async(
                server,
                host=host,
                port=port,
                path=args.path,
                log_level=args.log_level,
            )
        )
        return

    if args.command == "stdio":
        asyncio.run(run_stdio_transport_async(server))
        return

    parser.error(f"Unknown command: {args.command}")


def _describe_server(server) -> None:
    tools = [tool.name for tool in server.tools.list_tools()]
    settings = server.project_registry.settings
    print(f"Dev Workspace MCP ready: {server.name}")
    print(f"Projects: {len(server.project_registry.list_projects())}")
    print(f"HTTP: http://{settings.host}:{settings.port}/mcp")
    print("Tools:")
    for name in tools:
        print(f"- {name}")


if __name__ == "__main__":
    main()
