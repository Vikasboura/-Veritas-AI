"""
tests/unit/test_dedupe.py
──────────────────────────
Tests for document deduplication logic and re-ingest behaviour.
Uses the HTTP client so it exercises the full stack (service + routes).
"""
from __future__ import annotations

import hashlib
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import make_user_payload


# ── helpers ───────────────────────────────────────────────────────────────────

async def _register_login(client: AsyncClient) -> str:
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    r = await client.post("/api/v1/auth/token", json=payload)
    return r.json()["access_token"]


async def _create_workspace(client: AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/workspaces",
        json={"name": "DedupWS"},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()["id"]


def _fake_file(content: bytes = b"Hello World\n\nSecond paragraph.") -> dict:
    return {
        "file": ("test.txt", content, "text/plain"),
    }


# ── patch targets ─────────────────────────────────────────────────────────────

def _mock_enqueue():
    """Patch out the RQ enqueue so tests don't need Redis."""
    return patch(
        "app.services.document_service.enqueue_ingestion",
        return_value="fake-job-id",
    )


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_new_document(client: AsyncClient):
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    with _mock_enqueue():
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_upload_duplicate_identical_content(client: AsyncClient):
    """
    Uploading the exact same bytes twice must return the SAME document ID.
    When status is still 'pending' the service resets it and re-enqueues (same row).
    The content-hash dedup therefore prevents a second document row being created.
    """
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)
    content = b"Unique content ABC\n\nSecond paragraph."

    with _mock_enqueue():
        r1 = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(content),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r1.status_code == 202
    doc_id_1 = r1.json()["id"]

    # Upload the identical bytes again — same hash → same document row
    with _mock_enqueue():
        r2 = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(content),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r2.status_code == 202
    # Key assertion: no new row was created
    assert r2.json()["id"] == doc_id_1

    # Only one document should exist in the workspace
    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_upload_different_content_creates_new_doc(client: AsyncClient):
    """Different content → different hash → new document row."""
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    with _mock_enqueue():
        r1 = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(b"Content A\n\nParagraph two."),
            headers={"Authorization": f"Bearer {token}"},
        )
        r2 = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(b"Content B completely different\n\nOther paragraph."),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert r1.json()["id"] != r2.json()["id"]


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    with _mock_enqueue():
        await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(b"Doc one\n\nContent."),
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(b"Doc two\n\nDifferent content."),
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client: AsyncClient):
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    big_content = b"x" * (51 * 1024 * 1024)  # 51 MB
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        files={"file": ("big.txt", big_content, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_disallowed_extension(client: AsyncClient):
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_document_isolated_across_workspaces(client: AsyncClient):
    """Documents in workspace A must not appear when listing workspace B."""
    token_a = await _register_login(client)
    token_b = await _register_login(client)

    ws_a = await _create_workspace(client, token_a)
    ws_b = await _create_workspace(client, token_b)

    with _mock_enqueue():
        await client.post(
            f"/api/v1/workspaces/{ws_a}/documents",
            files=_fake_file(b"Secret doc in workspace A\n\nContent."),
            headers={"Authorization": f"Bearer {token_a}"},
        )

    resp = await client.get(
        f"/api/v1/workspaces/{ws_b}/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient):
    token = await _register_login(client)
    ws_id = await _create_workspace(client, token)

    with _mock_enqueue():
        r = await client.post(
            f"/api/v1/workspaces/{ws_id}/documents",
            files=_fake_file(),
            headers={"Authorization": f"Bearer {token}"},
        )
    doc_id = r.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    list_resp = await client.get(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(list_resp.json()) == 0
