#!/usr/bin/env python3
"""Start the MCP server temporarily and smoke-test the tools/list request."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from contextlib import closing

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def available_port() -> int:
    """Reserve an unused loopback port long enough to choose the smoke URL."""

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def list_tools(url: str) -> list[str]:
    """Return the tool names exposed by an initialized MCP session."""

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            return sorted(tool.name for tool in response.tools)


async def wait_for_tools(url: str, process: subprocess.Popen[bytes]) -> list[str]:
    """Retry while Uvicorn starts, surfacing an early server failure."""

    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MCP server exited with status {process.returncode}")
        try:
            return await list_tools(url)
        except Exception as exc:  # the HTTP endpoint is not ready yet
            last_error = exc
            await asyncio.sleep(0.5)
    raise TimeoutError(f"MCP server did not become ready: {last_error}")


def main() -> int:
    port = available_port()
    env = os.environ.copy()
    env.update({"HOST": "127.0.0.1", "PORT": str(port)})
    process = subprocess.Popen(
        [sys.executable, "-m", "mcp_airline.app"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        names = asyncio.run(wait_for_tools(f"http://127.0.0.1:{port}/mcp", process))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    if not names:
        print("tools/list returned no tools", file=sys.stderr)
        return 1

    print(f"tools/list OK ({len(names)} tools): {', '.join(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
