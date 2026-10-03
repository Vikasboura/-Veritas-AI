"""
app/models/semantic_cache.py
─────────────────────────────
Per-workspace semantic answer cache.
CRITICAL: workspace_id is mandatory on every query — cross-workspace
leakage is impossible because the ANN index filter enforces it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class SemanticCache(Base):
    __tablename__ = "semantic_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    question_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    question_emb: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    answer_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
