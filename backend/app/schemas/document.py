"""
app/schemas/document.py
────────────────────────
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


DocumentStatus = Literal["pending", "processing", "ready", "failed", "scanned_pdf"]


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    error_message: str | None
    page_count: int | None
    chunk_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """Returned immediately after upload; background job runs asynchronously."""
    id: uuid.UUID
    filename: str
    status: str
    message: str
