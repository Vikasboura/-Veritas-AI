"""
app/models/eval_run.py
───────────────────────
Eval experiment run: configuration, status, and results.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_eval_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    config_json: Mapped[dict] = mapped_column(JSONType, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    results_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
