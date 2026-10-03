"""
tests/unit/test_workspaces.py
──────────────────────────────
Unit tests for workspace creation, listing, and membership.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import make_user_payload


async def _register_and_login(client: AsyncClient, payload: dict | None = None) -> tuple[dict, str]:
    payload = payload or make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    token_resp = await client.post("/api/v1/auth/token", json=payload)
    token = token_resp.json()["access_token"]
    return payload, token


async def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient):
    _, token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "My Workspace"},
        headers=await _auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Workspace"
    assert data["role"] == "owner"


@pytest.mark.asyncio
async def test_list_workspaces(client: AsyncClient):
    _, token = await _register_and_login(client)
    headers = await _auth_header(token)
    await client.post("/api/v1/workspaces", json={"name": "WS1"}, headers=headers)
    await client.post("/api/v1/workspaces", json={"name": "WS2"}, headers=headers)
    resp = await client.get("/api/v1/workspaces", headers=headers)
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert "WS1" in names
    assert "WS2" in names


@pytest.mark.asyncio
async def test_workspace_isolation(client: AsyncClient):
    """User A's workspaces must not appear in User B's listing."""
    _, token_a = await _register_and_login(client)
    _, token_b = await _register_and_login(client)

    await client.post(
        "/api/v1/workspaces",
        json={"name": "Secret WS"},
        headers=await _auth_header(token_a),
    )
    resp = await client.get("/api/v1/workspaces", headers=await _auth_header(token_b))
    names = [w["name"] for w in resp.json()]
    assert "Secret WS" not in names


@pytest.mark.asyncio
async def test_get_workspace_as_member(client: AsyncClient):
    payload_a, token_a = await _register_and_login(client)
    payload_b, token_b = await _register_and_login(client)

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Shared WS"},
        headers=await _auth_header(token_a),
    )
    ws_id = ws_resp.json()["id"]

    # Add B as member
    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": payload_b["email"], "role": "member"},
        headers=await _auth_header(token_a),
    )

    resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=await _auth_header(token_b))
    assert resp.status_code == 200
    assert resp.json()["role"] == "member"


@pytest.mark.asyncio
async def test_get_workspace_unauthorized(client: AsyncClient):
    _, token_a = await _register_and_login(client)
    _, token_b = await _register_and_login(client)

    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Private"},
        headers=await _auth_header(token_a),
    )
    ws_id = ws_resp.json()["id"]

    resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=await _auth_header(token_b))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_add_member_requires_owner(client: AsyncClient):
    """A member (not owner) should not be able to add other members."""
    payload_a, token_a = await _register_and_login(client)
    payload_b, token_b = await _register_and_login(client)
    payload_c, _ = await _register_and_login(client)

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "WS"}, headers=await _auth_header(token_a)
    )
    ws_id = ws_resp.json()["id"]

    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": payload_b["email"], "role": "member"},
        headers=await _auth_header(token_a),
    )

    # B tries to add C — should fail (B is only a member, not owner)
    resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": payload_c["email"], "role": "member"},
        headers=await _auth_header(token_b),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_workspace_by_owner(client: AsyncClient):
    _, token = await _register_and_login(client)
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "ToDelete"}, headers=await _auth_header(token)
    )
    ws_id = ws_resp.json()["id"]
    del_resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}", headers=await _auth_header(token)
    )
    assert del_resp.status_code == 204
