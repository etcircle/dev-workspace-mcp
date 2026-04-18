from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from dev_workspace_mcp.mcp_server.server import create_server
from dev_workspace_mcp.mcp_server.transport_http import run_http_transport_async


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
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
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
