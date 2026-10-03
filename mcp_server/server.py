"""
mcp_server/server.py
─────────────────────
CiteBase Pro Model Context Protocol (MCP) server.
Exposes workspace search and grounded question-answering tools over stdio JSON-RPC.
Compatible with Claude Desktop, Cursor, Antigravity, and all MCP-compliant clients.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp_server.tools import search_workspace_documents, ask_workspace

API_BASE_URL = os.environ.get("CITEBASE_API_URL", "http://localhost:8000/api/v1")
API_KEY = os.environ.get("CITEBASE_API_KEY", "")

TOOLS = [
    {
        "name": "search_docs",
        "description": "Search documents within a specific CiteBase Pro workspace. Returns passages with filenames, page numbers, and similarity scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "The UUID of the workspace to search in.",
                },
                "query": {
                    "type": "string",
                    "description": "The keyword or semantic search query.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of candidate chunks to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["workspace_id", "query"],
        },
    },
    {
        "name": "ask_workspace",
        "description": "Ask a question against workspace documents. Returns a grounded answer with verifiable citations and refusal status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "The UUID of the workspace.",
                },
                "question": {
                    "type": "string",
                    "description": "The question to answer.",
                },
            },
            "required": ["workspace_id", "question"],
        },
    },
]


def send_response(response: dict[str, Any]) -> None:
    body = json.dumps(response)
    sys.stdout.write(f"Content-Length: {len(body)}\r\n\r\n{body}")
    sys.stdout.flush()


async def handle_request(req: dict[str, Any]) -> dict[str, Any] | None:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "citebase-pro-mcp", "version": "1.0.0"},
            },
        }

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool_name == "search_docs":
                res = await search_workspace_documents(
                    api_base_url=API_BASE_URL,
                    api_key=API_KEY,
                    workspace_id=args["workspace_id"],
                    query=args["query"],
                    top_k=args.get("top_k", 5),
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
                    },
                }

            elif tool_name == "ask_workspace":
                res = await ask_workspace(
                    api_base_url=API_BASE_URL,
                    api_key=API_KEY,
                    workspace_id=args["workspace_id"],
                    question=args["question"],
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, indent=2)}]
                    },
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }

        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


async def main():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break

        line_str = line.decode("utf-8").strip()
        if line_str.startswith("Content-Length:"):
            length = int(line_str.split(":")[1].strip())
            # Read empty separator line
            await reader.readline()
            # Read JSON body
            body_bytes = await reader.readexactly(length)
            req = json.loads(body_bytes.decode("utf-8"))
            resp = await handle_request(req)
            if resp is not None:
                send_response(resp)


if __name__ == "__main__":
    asyncio.run(main())
