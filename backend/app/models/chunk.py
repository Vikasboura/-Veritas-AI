"""
app/models/chunk.py
────────────────────
Chunk ORM model.
Stores both the pgvector embedding and a tsvector for hybrid search.
The fts_vector is populated server-side via a Postgres trigger (defined in the
Alembic migration), so we never need to compute it in Python.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized for efficient WHERE workspace_id = :wid in retrieval
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_cleaned: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # pgvector column — dimension set via server migration, must match EMBEDDING_DIM
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)

    # tsvector — maintained by Postgres trigger, never set from Python
    # We declare it as a passthrough Text so SQLAlchemy can read it
    # (actual type is TSVECTOR in Postgres, we use Text here since we never write it)
    fts_vector: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relationships
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
