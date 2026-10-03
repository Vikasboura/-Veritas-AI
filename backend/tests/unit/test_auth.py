"""
tests/unit/test_auth.py
────────────────────────
Unit tests for auth service and routes.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import make_user_payload


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    payload = make_user_payload()
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == payload["email"]
    assert "id" in data
    assert "pw_hash" not in data  # never leak hash


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password_no_uppercase(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@test.com", "password": "nouppercase1"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password_no_digit(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@test.com", "password": "NoDigitHere"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/token", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post(
        "/api/v1/auth/token",
        json={"email": payload["email"], "password": "WrongPass9"},
    )
    assert resp.status_code == 401
    # Generic message — must not reveal whether email exists
    assert resp.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/token",
        json={"email": "ghost@test.com", "password": "GhostPass1"},
    )
    assert resp.status_code == 401
    # Same message as wrong password (prevents enumeration)
    assert resp.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    token_resp = await client.post("/api/v1/auth/token", json=payload)
    token = token_resp.json()["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == payload["email"]


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    token_resp = await client.post("/api/v1/auth/token", json=payload)
    refresh_token = token_resp.json()["refresh_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client: AsyncClient):
    """Access tokens must not be accepted as refresh tokens."""
    payload = make_user_payload()
    await client.post("/api/v1/auth/register", json=payload)
    token_resp = await client.post("/api/v1/auth/token", json=payload)
    access_token = token_resp.json()["access_token"]
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
