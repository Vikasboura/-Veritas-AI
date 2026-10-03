"""
app/services/auth_service.py
─────────────────────────────
Business logic for user registration and login.
All DB access goes through SQLAlchemy; no raw SQL here.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.auth import RegisterRequest

log = get_logger(__name__)


class AuthError(Exception):
    """Raised for invalid credentials or duplicate accounts."""


async def register_user(db: AsyncSession, req: RegisterRequest) -> User:
    """
    Create a new user. Raises AuthError if email already exists.
    """
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    if result.scalar_one_or_none():
        raise AuthError("Email already registered")

    user = User(
        email=req.email.lower(),
        pw_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info("user_registered", user_id=str(user.id))
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> tuple[str, str]:
    """
    Verify credentials and return (access_token, refresh_token).
    Raises AuthError on failure (use generic message to prevent enumeration).
    """
    result = await db.execute(select(User).where(User.email == email.lower()))
    user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(password, user.pw_hash):
        raise AuthError("Invalid credentials")

    if not user.is_active:
        raise AuthError("Account is deactivated")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    log.info("user_login", user_id=str(user.id))
    return access_token, refresh_token


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
