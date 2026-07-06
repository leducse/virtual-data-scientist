#!/usr/bin/env python3
"""Minimal stdio MCP server for the virtual data scientist tools.

This implements the JSON-RPC surface needed by MCP hosts:

- initialize
- tools/list
- tools/call

It intentionally delegates business logic to `mcp_server.tools`, which in turn
calls the existing local app API. That keeps MCP, UI, and AgentCore handoffs on
one persistence path.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from mcp_server.tools import TOOL_DEFINITIONS, call_tool


def response(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")

    if method == "initialize":
        return response(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "virtual-data-scientist",
                    "version": "0.1.0",
                },
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return response(message_id, {"tools": TOOL_DEFINITIONS})

    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(name, arguments)
            return response(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, default=str),
                        }
                    ],
                    "isError": False,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive stdio boundary
            return response(
                message_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )

    return error_response(message_id, -32601, f"Method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            outgoing = handle(message)
        except Exception as exc:  # pragma: no cover - defensive stdio boundary
            outgoing = error_response(None, -32603, f"{exc}\n{traceback.format_exc()}")
        if outgoing is not None:
            sys.stdout.write(json.dumps(outgoing) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
