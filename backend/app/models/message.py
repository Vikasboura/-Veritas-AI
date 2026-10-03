"""
app/models/message.py
──────────────────────
Stores user and assistant messages with citations as JSON.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import JSONType


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{chunk_id, doc_id, doc_filename, page_number, chunk_text}]
    citations_json: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")  # noqa: F821
    feedback: Mapped[list["Feedback"]] = relationship(  # noqa: F821
        "Feedback", back_populates="message", cascade="all, delete-orphan"
    )
