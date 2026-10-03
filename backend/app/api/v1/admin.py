"""
app/api/v1/admin.py
───────────────────
Admin observability endpoints:
  - GET /api/v1/admin/traces (recent traces)
  - GET /api/v1/admin/refused (refusals log)
  - GET /api/v1/admin/feedback/negative (thumbs down feedback)
  - GET /api/v1/admin/ingestion/failures (failed ingestion jobs)
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.trace import Trace
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/traces", summary="Recent query traces")
async def get_recent_traces(
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    query = select(Trace).order_by(Trace.created_at.desc()).limit(limit)
    res = await db.execute(query)
    traces = res.scalars().all()
    return [
        {
            "id": str(t.id),
            "request_id": str(t.request_id),
            "workspace_id": str(t.workspace_id),
            "query_original": t.query_original,
            "refused": t.refused,
            "cache_hit": t.cache_hit,
            "total_latency_ms": t.total_latency_ms,
            "created_at": t.created_at.isoformat(),
        }
        for t in traces
    ]


@router.get("/refused", summary="Low-confidence refusals log")
async def get_refused_queries(
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    query = (
        select(Message)
        .where(Message.refused == True)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(query)
    messages = res.scalars().all()
    return [
        {
            "id": str(m.id),
            "session_id": str(m.session_id),
            "content": m.content,
            "refusal_reason": m.refusal_reason,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.get("/feedback/negative", summary="Negative thumbs-down feedback")
async def get_negative_feedback(
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    query = (
        select(Feedback)
        .where(Feedback.rating == -1)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(query)
    feedback_items = res.scalars().all()
    return [
        {
            "id": str(f.id),
            "message_id": str(f.message_id),
            "user_id": str(f.user_id),
            "comment": f.comment,
            "created_at": f.created_at.isoformat(),
        }
        for f in feedback_items
    ]


@router.get("/ingestion/failures", summary="Failed document ingestion jobs")
async def get_ingestion_failures(
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    query = (
        select(Document)
        .where(Document.status.in_(["failed", "scanned_pdf"]))
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(query)
    failed_docs = res.scalars().all()
    return [
        {
            "id": str(d.id),
            "workspace_id": str(d.workspace_id),
            "filename": d.filename,
            "status": d.status,
            "error_message": d.error_message,
            "created_at": d.created_at.isoformat(),
        }
        for d in failed_docs
    ]
