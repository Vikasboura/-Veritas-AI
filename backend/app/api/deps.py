"""
app/api/deps.py
────────────────
FastAPI dependencies for authentication, DB session, and workspace access control.
These are the sole gatekeepers — every protected route must use them.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import extract_user_id
from app.db.session import DbSession
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services import auth_service, workspace_service

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    """
    Validate Bearer token and return the authenticated User.
    Raises HTTP 401 for any invalid/missing token.
    """
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id_str = extract_user_id(credentials.credentials, expected_type="access")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user = await auth_service.get_user_by_id(db, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_workspace_member(
    workspace_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMember:
    """Ensure the current user is a member of the workspace."""
    try:
        return await workspace_service.require_member(db, workspace_id, current_user.id)
    except workspace_service.WorkspacePermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a workspace member")
    except workspace_service.WorkspaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


WorkspaceMemberDep = Annotated[WorkspaceMember, Depends(get_workspace_member)]


async def get_workspace_owner(
    workspace_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMember:
    """Ensure the current user is the owner of the workspace."""
    try:
        return await workspace_service.require_owner(db, workspace_id, current_user.id)
    except workspace_service.WorkspacePermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner role required")
    except workspace_service.WorkspaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


WorkspaceOwnerDep = Annotated[WorkspaceMember, Depends(get_workspace_owner)]
