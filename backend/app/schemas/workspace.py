"""
app/schemas/workspace.py
─────────────────────────
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime
    role: str | None = None  # caller's role — populated by service layer

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    email: str
    role: Literal["member", "owner"] = "member"


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}
