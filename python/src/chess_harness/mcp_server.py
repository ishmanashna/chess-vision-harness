"""MCP stdio server entry point for Chess Vision Harness."""

from __future__ import annotations

import asyncio

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool

from . import bootstrap  # noqa: F401
from .tools_mcp import get_mcp_instance

server = Server("chess-vision-harness")


def _harness():
    return get_mcp_instance()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _harness().get_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    return await _harness().handle_tool_call(name, arguments)


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
