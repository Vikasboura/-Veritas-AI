"""
app/db/session.py
─────────────────
Async SQLAlchemy engine and session factory.
Use get_db() as a FastAPI dependency for request-scoped sessions.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    # SQLite (used in tests) doesn't support pool_size / max_overflow.
    # StaticPool keeps a single connection which is required for in-memory SQLite.
    **(
        {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        if _is_sqlite
        else {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}
    ),
    echo=settings.ENVIRONMENT == "development",
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Convenience type alias for route signatures
DbSession = Annotated[AsyncSession, Depends(get_db)]
