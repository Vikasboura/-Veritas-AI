"""
app/schemas/eval.py
────────────────────
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvalConfig(BaseModel):
    """Configuration for a single eval experiment."""
    name: str
    golden_dataset_path: str  # relative to /eval/golden/
    hybrid_enabled: bool = True
    reranker_enabled: bool = True
    top_k_vector: int = 20
    top_k_fts: int = 20
    top_n_rerank: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 64


class EvalRunCreate(BaseModel):
    config: EvalConfig


class EvalRunResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    config: dict[str, Any]
    results: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class TraceResponse(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    workspace_id: uuid.UUID
    query_original: str
    query_rewritten: str | None
    retrieval_steps: list | None
    rerank_order: list | None
    llm_calls: list | None
    grounding_result: dict | None
    cache_hit: bool | None
    refused: bool | None
    total_latency_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
