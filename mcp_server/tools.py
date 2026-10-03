"""
mcp_server/tools.py
───────────────────
Tool definitions and schemas for CiteBase Pro Model Context Protocol (MCP) server.
"""
from __future__ import annotations

from typing import Any
import httpx


async def search_workspace_documents(
    api_base_url: str,
    api_key: str,
    workspace_id: str,
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Search documents within a specific CiteBase Pro workspace.
    Returns matching chunk passages, filenames, page numbers, and relevance scores.
    """
    url = f"{api_base_url}/workspaces/{workspace_id}/chat?stream=false"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"question": query}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"CiteBase API returned {resp.status_code}: {resp.text}")

        data = resp.json()
        citations = data.get("citations", [])
        return [
            {
                "chunk_id": c.get("chunk_id"),
                "document_filename": c.get("doc_filename"),
                "page_number": c.get("page_number"),
                "score": c.get("score"),
                "text": c.get("chunk_text"),
            }
            for c in citations[:top_k]
        ]


async def ask_workspace(
    api_base_url: str,
    api_key: str,
    workspace_id: str,
    question: str,
) -> dict[str, Any]:
    """
    Ask a question against a CiteBase Pro workspace.
    Returns strictly grounded answer, refusal decision, and source citations.
    """
    url = f"{api_base_url}/workspaces/{workspace_id}/chat?stream=false"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"question": question}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"CiteBase API returned {resp.status_code}: {resp.text}")
        return resp.json()
