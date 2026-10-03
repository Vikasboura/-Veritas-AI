"""
app/api/v1/traces.py
────────────────────
Trace retrieval endpoint.
"""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.db.session import get_db
from app.models.user import User
from app.schemas.eval import TraceResponse
from app.services.trace_service import TraceService

router = APIRouter(prefix="/workspaces/{workspace_id}/traces", tags=["traces"])


@router.get(
    "/{request_id}",
    response_model=TraceResponse,
    summary="Get execution trace for a query request",
)
async def get_trace(
    workspace_id: uuid.UUID,
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_member),
) -> TraceResponse:
    trace = await TraceService.get_trace_by_request_id(db, workspace_id, request_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    return TraceResponse.model_validate(trace)
