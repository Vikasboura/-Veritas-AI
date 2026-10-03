"""
app/schemas/chat.py
────────────────────
Schemas for chat endpoints and SSE stream events.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4096)
    session_id: uuid.UUID | None = None  # create new session if absent


class Citation(BaseModel):
    chunk_id: uuid.UUID
    doc_id: uuid.UUID
    doc_filename: str
    page_number: int | None
    chunk_text: str
    score: float | None = None


class ChatResponse(BaseModel):
    """Non-streaming response (used in tests and cache hits)."""
    message_id: uuid.UUID
    session_id: uuid.UUID
    answer: str
    citations: list[Citation]
    refused: bool
    refusal_reason: str | None
    request_id: uuid.UUID


# ── SSE event models ──────────────────────────────────────────────────────────
class SSEDelta(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class SSECitation(BaseModel):
    type: Literal["citation"] = "citation"
    citations: list[Citation]


class SSEDone(BaseModel):
    type: Literal["done"] = "done"
    message_id: uuid.UUID
    session_id: uuid.UUID
    refused: bool
    refusal_reason: str | None = None
    request_id: uuid.UUID


class SSEError(BaseModel):
    type: Literal["error"] = "error"
    error: str
    request_id: uuid.UUID


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    citations: list[Citation]
    refused: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackRequest(BaseModel):
    rating: Literal[1, -1]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rating: int
    created_at: datetime

    model_config = {"from_attributes": True}
