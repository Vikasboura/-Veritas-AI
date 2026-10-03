"""
app/services/workspace_service.py
───────────────────────────────────
Workspace CRUD and membership management.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.workspace import Workspace, WorkspaceMember
from app.models.user import User
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, MemberResponse

log = get_logger(__name__)


class WorkspaceError(Exception):
    pass


class WorkspaceNotFoundError(WorkspaceError):
    pass


class WorkspacePermissionError(WorkspaceError):
    pass


async def create_workspace(
    db: AsyncSession, name: str, owner: User
) -> Workspace:
    ws = Workspace(name=name, owner_id=owner.id)
    db.add(ws)
    await db.flush()  # get ws.id before adding member
    # Owner is automatically a member with role='owner'
    member = WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(ws)
    log.info("workspace_created", workspace_id=str(ws.id), owner_id=str(owner.id))
    return ws


async def list_workspaces(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Return workspaces the user is a member of, with their role."""
    stmt = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {**WorkspaceResponse.model_validate(ws).model_dump(), "role": role}
        for ws, role in rows
    ]


async def get_workspace_or_404(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise WorkspaceNotFoundError(f"Workspace {workspace_id} not found")
    return ws


async def get_member(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_member(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember:
    m = await get_member(db, workspace_id, user_id)
    if not m:
        raise WorkspacePermissionError("Not a member of this workspace")
    return m


async def require_owner(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember:
    m = await require_member(db, workspace_id, user_id)
    if m.role != "owner":
        raise WorkspacePermissionError("Owner role required")
    return m


async def add_member(
    db: AsyncSession, workspace_id: uuid.UUID, email: str, role: str, acting_user_id: uuid.UUID
) -> WorkspaceMember:
    # Caller must already be owner — enforced at route level
    result = await db.execute(select(User).where(User.email == email.lower()))
    target: User | None = result.scalar_one_or_none()
    if not target:
        raise WorkspaceError(f"No user with email {email}")

    existing = await get_member(db, workspace_id, target.id)
    if existing:
        existing.role = role
        await db.commit()
        return existing

    member = WorkspaceMember(workspace_id=workspace_id, user_id=target.id, role=role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    log.info("member_added", workspace_id=str(workspace_id), user_id=str(target.id), role=role)
    return member


async def remove_member(
    db: AsyncSession, workspace_id: uuid.UUID, target_user_id: uuid.UUID, acting_user_id: uuid.UUID
) -> None:
    if target_user_id == acting_user_id:
        raise WorkspaceError("Cannot remove yourself from a workspace")
    m = await get_member(db, workspace_id, target_user_id)
    if not m:
        raise WorkspaceNotFoundError("Member not found")
    await db.delete(m)
    await db.commit()
    log.info("member_removed", workspace_id=str(workspace_id), user_id=str(target_user_id))


async def delete_workspace(
    db: AsyncSession, workspace_id: uuid.UUID, acting_user_id: uuid.UUID
) -> None:
    ws = await get_workspace_or_404(db, workspace_id)
    if ws.owner_id != acting_user_id:
        raise WorkspacePermissionError("Only the owner can delete the workspace")
    await db.delete(ws)
    await db.commit()
    log.info("workspace_deleted", workspace_id=str(workspace_id))
