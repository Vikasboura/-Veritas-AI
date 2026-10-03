"""
app/api/v1/workspaces.py
─────────────────────────
Workspace CRUD + member management routes.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, WorkspaceMemberDep, WorkspaceOwnerDep
from app.schemas.workspace import MemberAdd, MemberResponse, WorkspaceCreate, WorkspaceResponse
from app.services import workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate, db: DbSession, current_user: CurrentUser
) -> WorkspaceResponse:
    ws = await workspace_service.create_workspace(db, body.name, current_user)
    return WorkspaceResponse(
        id=ws.id, name=ws.name, owner_id=ws.owner_id, created_at=ws.created_at, role="owner"
    )


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(db: DbSession, current_user: CurrentUser) -> list[WorkspaceResponse]:
    items = await workspace_service.list_workspaces(db, current_user.id)
    return [WorkspaceResponse(**item) for item in items]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    db: DbSession,
    member: WorkspaceMemberDep,
) -> WorkspaceResponse:
    ws = await workspace_service.get_workspace_or_404(db, workspace_id)
    return WorkspaceResponse(
        id=ws.id, name=ws.name, owner_id=ws.owner_id, created_at=ws.created_at, role=member.role
    )


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_workspace(
    workspace_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    _: WorkspaceOwnerDep,
) -> None:
    try:
        await workspace_service.delete_workspace(db, workspace_id, current_user.id)
    except workspace_service.WorkspacePermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: uuid.UUID,
    body: MemberAdd,
    db: DbSession,
    current_user: CurrentUser,
    _: WorkspaceOwnerDep,
) -> MemberResponse:
    try:
        m = await workspace_service.add_member(db, workspace_id, body.email, body.role, current_user.id)
    except workspace_service.WorkspaceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == m.user_id))
    u = result.scalar_one()
    return MemberResponse(user_id=m.user_id, email=u.email, role=m.role, joined_at=m.joined_at)


@router.delete("/{workspace_id}/members/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_member(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    _: WorkspaceOwnerDep,
) -> None:
    try:
        await workspace_service.remove_member(db, workspace_id, target_user_id, current_user.id)
    except workspace_service.WorkspaceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except workspace_service.WorkspaceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
