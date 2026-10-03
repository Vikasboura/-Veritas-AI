"""
tests/conftest.py
──────────────────
Shared fixtures for all tests.
Uses an in-memory SQLite database for unit tests and an optional
real Postgres DB (via TEST_DATABASE_URL env var) for integration tests.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ── Override settings BEFORE importing app ─────────────────────────────────
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-purposes-only-32x")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("PULSEWATCH_ENABLED", "false")
os.environ.setdefault("EMBEDDING_DIM", "384")

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


# ── Engine scoped to test session ─────────────────────────────────────────
@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    # Use real Postgres for integration tests if env var is set
    db_url = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = create_async_engine(db_url, echo=False)

    # SQLite doesn't support pgvector — skip vector column during unit tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB dependency overridden to use the test session."""
    app = create_app()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Mock LLM client ────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm_client():
    """
    Returns a mock that mimics the OpenAI-compatible client interface.
    Use in tests that exercise services making LLM calls.
    """
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="Mocked LLM response"))],
        usage=MagicMock(prompt_tokens=100, completion_tokens=50),
        model="mock-model",
    ))
    return client


# ── Convenience factories ──────────────────────────────────────────────────
def make_user_payload(email: str | None = None) -> dict[str, Any]:
    unique = uuid.uuid4().hex[:8]
    return {
        "email": email or f"test_{unique}@example.com",
        "password": "TestPass1",
    }
