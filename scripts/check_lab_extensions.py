#!/usr/bin/env python3
"""Check the learner-added tools against the lab's documented interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def check_wikipedia() -> None:
    """Confirm that the environment can reach the source used by airport_info."""

    request = urllib.request.Request(
        "https://en.wikipedia.org/api/rest_v1/page/summary/Pittsburgh_International_Airport",
        headers={"User-Agent": "mlip-tool-calling-lab/1.0 (course smoke test)"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    if payload.get("title") != "Pittsburgh International Airport":
        raise RuntimeError("Wikipedia returned an unexpected airport summary")


def checked_text(label: str, result: object) -> str:
    """Reject MCP errors and flatten textual result content."""

    if getattr(result, "isError", False):
        raise RuntimeError(f"{label} returned an MCP error")
    content = getattr(result, "content", [])
    return "\n".join(item.text for item in content if item.type == "text")


async def fetch_tool_results(
    url: str, injection_arguments: dict[str, object]
) -> tuple[set[str], object | None, object | None, object | None]:
    """Fetch results while keeping validation errors outside MCP task groups."""

    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            schemas = {tool.name: tool.inputSchema for tool in listed.tools}
            missing = {"current_time", "airport_info"} - schemas.keys()
            if missing:
                return missing, None, None, None

            current = await session.call_tool("current_time", {})
            normal = await session.call_tool("airport_info", {"iata_code": "PIT"})
            injected = await session.call_tool("airport_info", injection_arguments)
            return missing, current, normal, injected


def validate_tool_results(
    results: tuple[set[str], object | None, object | None, object | None],
) -> None:
    """Validate calls after MCP context managers have shut down cleanly."""

    missing, current_result, normal_result, injected_result = results
    if missing:
        raise RuntimeError(f"tools/list is missing: {', '.join(sorted(missing))}")
    assert current_result is not None
    assert normal_result is not None
    assert injected_result is not None

    current = checked_text("current_time", current_result)
    if not current.strip():
        raise RuntimeError("current_time returned an empty result")
    if not any(marker in current.upper() for marker in ("UTC", "+00:00", "Z")):
        raise RuntimeError("current_time did not identify its result as UTC")

    normal = checked_text("airport_info", normal_result)
    if not normal.strip() or "PIT" not in normal.upper():
        raise RuntimeError("airport_info did not return information for PIT")

    injected = checked_text("airport_info injection stub", injected_result)
    if not injected.strip() or injected == normal:
        raise RuntimeError("the airport_info injection stub was not observable")

    print(f"current_time OK: {current}")
    print("airport_info OK for PIT")
    print("airport_info injection stub OK (result differs from live lookup)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check learner-added tools on a running airline MCP server."
    )
    parser.add_argument("--url", default="http://localhost:3000/mcp")
    parser.add_argument(
        "--injection-json",
        default='{"iata_code":"PIT","simulate_injection":true}',
        help="JSON arguments that activate your airport_info stub",
    )
    args = parser.parse_args()

    injection_arguments = json.loads(args.injection_json)
    if not isinstance(injection_arguments, dict):
        parser.error("--injection-json must decode to an object")

    check_wikipedia()
    print("Outbound Wikipedia access OK", flush=True)
    results = asyncio.run(fetch_tool_results(args.url, injection_arguments))
    validate_tool_results(results)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Lab extension check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
