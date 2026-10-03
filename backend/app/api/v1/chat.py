"""
app/api/v1/chat.py
──────────────────
Chat endpoints:
  - POST /api/v1/workspaces/{workspace_id}/chat (SSE streaming or JSON)
  - GET  /api/v1/workspaces/{workspace_id}/sessions
  - GET  /api/v1/workspaces/{workspace_id}/sessions/{session_id}/messages
  - POST /api/v1/messages/{message_id}/feedback
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.db.session import get_db
from app.models.chat_session import ChatSession
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Citation,
    FeedbackRequest,
    FeedbackResponse,
    MessageResponse,
    SessionResponse,
)
from app.services.generation_service import GenerationService

router = APIRouter(tags=["chat"])


@router.post(
    "/workspaces/{workspace_id}/chat",
    summary="Ask a question against workspace documents",
    response_model=None,
)
async def chat_endpoint(
    workspace_id: uuid.UUID,
    payload: ChatRequest,
    request: Request,
    stream: bool = Query(default=True, description="Stream response tokens via SSE"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_member),
) -> Any:
    """
    Submits a query to the RAG pipeline.
    By default streams SSE events (type: citation, delta, done, error).
    When stream=false, returns standard ChatResponse JSON.
    """
    request_id_str = getattr(request.state, "request_id", None)
    req_id = uuid.UUID(request_id_str) if request_id_str else uuid.uuid4()

    if stream:
        return StreamingResponse(
            GenerationService.stream_answer(
                db=db,
                workspace_id=workspace_id,
                user_id=current_user.id,
                question=payload.question,
                session_id=payload.session_id,
                request_id=req_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Request-ID": str(req_id),
            },
        )

    # Non-streaming JSON response
    response = await GenerationService.generate_answer(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        question=payload.question,
        session_id=payload.session_id,
        request_id=req_id,
    )
    return response


@router.get(
    "/workspaces/{workspace_id}/sessions",
    response_model=list[SessionResponse],
    summary="List chat sessions in a workspace",
)
async def list_sessions(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_member),
) -> list[SessionResponse]:
    query = (
        select(ChatSession)
        .where(
            ChatSession.workspace_id == workspace_id,
            ChatSession.user_id == current_user.id,
        )
        .order_by(ChatSession.created_at.desc())
    )
    res = await db.execute(query)
    sessions = res.scalars().all()
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get(
    "/workspaces/{workspace_id}/sessions/{session_id}/messages",
    response_model=list[MessageResponse],
    summary="Get message history for a chat session",
)
async def get_session_messages(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_member),
) -> list[MessageResponse]:
    # Check session ownership
    sess_query = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.workspace_id == workspace_id,
    )
    res = await db.execute(sess_query)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    msg_query = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    msg_res = await db.execute(msg_query)
    messages = msg_res.scalars().all()

    output: list[MessageResponse] = []
    for m in messages:
        citations = [Citation(**c) for c in (m.citations_json or [])]
        output.append(
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                citations=citations,
                refused=m.refused,
                created_at=m.created_at,
            )
        )
    return output


@router.post(
    "/messages/{message_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit thumbs up/down feedback on an assistant message",
)
async def submit_feedback(
    message_id: uuid.UUID,
    payload: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackResponse:
    # Verify message exists
    msg_query = select(Message).where(Message.id == message_id)
    res = await db.execute(msg_query)
    message = res.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    feedback = Feedback(
        id=uuid.uuid4(),
        message_id=message.id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback)
