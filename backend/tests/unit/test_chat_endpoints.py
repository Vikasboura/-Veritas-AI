"""
tests/unit/test_chat_endpoints.py
───────────────────────────────────
Unit tests for Chat API endpoints:
  - Non-streaming chat endpoint (stream=false)
  - Streaming SSE chat endpoint (stream=true)
  - Chat session listing and message history
  - Message feedback submission (+1 / -1)
  - Refusal when workspace has no documents
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient

from tests.conftest import make_user_payload


async def _register_login_create_ws(client: AsyncClient) -> tuple[str, str]:
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    tok = await client.post("/api/v1/auth/token", json=payload)
    token = tok.json()["access_token"]

    ws = await client.post(
        "/api/v1/workspaces",
        json={"name": "ChatTestWS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    ws_id = ws.json()["id"]
    return token, ws_id


class MockLLM:
    async def create_chat_completion(self, messages, **kwargs):
        return "Based on the documents, the deployment date is June 1st [1].", {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
            "model": "mock-llm",
        }

    async def create_chat_stream(self, messages, **kwargs):
        tokens = ["Based ", "on the ", "documents, ", "the deployment ", "date is June 1st [1]."]
        for t in tokens:
            yield t


@pytest.mark.asyncio
async def test_chat_refusal_when_no_documents(client: AsyncClient):
    """When a workspace has no indexed documents, the system refuses to answer."""
    token, ws_id = await _register_login_create_ws(client)

    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/chat?stream=false",
        json={"question": "What is the secret launch date?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is True
    assert data["refusal_reason"] == "NO_RELEVANT_CHUNKS"
    assert "No relevant documents were found" in data["answer"]
    assert len(data["citations"]) == 0


@pytest.mark.asyncio
async def test_chat_non_streaming_success(client: AsyncClient):
    token, ws_id = await _register_login_create_ws(client)

    # Mock retrieval returning 1 candidate chunk
    from app.services.retrieval_service import RetrievedChunk
    import uuid

    mock_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename="specs.pdf",
        workspace_id=uuid.UUID(ws_id),
        page_number=3,
        section_title="Timeline",
        content="Deployment is scheduled for June 1st.",
        content_cleaned="Deployment is scheduled for June 1st.",
        final_score=0.95,
    )

    with patch("app.services.generation_service.RetrievalService.retrieve", return_value=[mock_chunk]):
        with patch("app.services.generation_service.get_llm_client", return_value=MockLLM()):
            resp = await client.post(
                f"/api/v1/workspaces/{ws_id}/chat?stream=false",
                json={"question": "When is the deployment?"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["refused"] is False
            assert "June 1st" in data["answer"]
            assert len(data["citations"]) == 1
            assert data["citations"][0]["doc_filename"] == "specs.pdf"
            assert data["citations"][0]["page_number"] == 3


@pytest.mark.asyncio
async def test_chat_streaming_sse(client: AsyncClient):
    token, ws_id = await _register_login_create_ws(client)

    from app.services.retrieval_service import RetrievedChunk
    import uuid

    mock_chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename="handbook.pdf",
        workspace_id=uuid.UUID(ws_id),
        page_number=1,
        section_title="Policies",
        content="Vacation policy details.",
        content_cleaned="Vacation policy details.",
        final_score=0.88,
    )

    with patch("app.services.generation_service.RetrievalService.retrieve", return_value=[mock_chunk]):
        with patch("app.services.generation_service.get_llm_client", return_value=MockLLM()):
            resp = await client.post(
                f"/api/v1/workspaces/{ws_id}/chat?stream=true",
                json={"question": "What is the vacation policy?"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = resp.text.strip().split("\n\n")
            event_types = []
            for line in lines:
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    event_types.append(payload.get("type"))

            assert "citation" in event_types
            assert "delta" in event_types
            assert "done" in event_types


@pytest.mark.asyncio
async def test_sessions_and_messages_history(client: AsyncClient):
    token, ws_id = await _register_login_create_ws(client)

    # Ask a question to generate a session
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/chat?stream=false",
        json={"question": "Question for session test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    msg_data = resp.json()
    sess_id = msg_data["session_id"]
    msg_id = msg_data["message_id"]

    # List sessions
    sessions_res = await client.get(
        f"/api/v1/workspaces/{ws_id}/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 1
    assert any(s["id"] == sess_id for s in sessions)

    # Get message history
    history_res = await client.get(
        f"/api/v1/workspaces/{ws_id}/sessions/{sess_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) == 2  # user message and assistant message
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # Submit feedback on assistant message
    fb_res = await client.post(
        f"/api/v1/messages/{msg_id}/feedback",
        json={"rating": 1, "comment": "Accurate and clear"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fb_res.status_code == 201
    assert fb_res.json()["rating"] == 1
