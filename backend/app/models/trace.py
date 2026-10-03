"""
app/models/trace.py
────────────────────
Full per-request trace: retrieval steps, rerank, LLM calls, latency.
All heavy detail is stored as JSONB to keep the schema flexible.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    query_original: Mapped[str] = mapped_column(Text, nullable=False)
    query_rewritten: Mapped[str | None] = mapped_column(Text, nullable=True)

    # [{step: str, candidates: [{chunk_id, score}], latency_ms: int}]
    retrieval_steps: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    rerank_order: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    # [{model, prompt_tokens, completion_tokens, latency_ms, cost_usd}]
    llm_calls: Mapped[list | None] = mapped_column(JSONType, nullable=True)

    grounding_result: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    cache_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refused: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
