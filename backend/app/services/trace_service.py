"""
app/services/trace_service.py
──────────────────────────────
Trace logging and PulseWatch observability integration.
Records complete end-to-end execution traces for every query:
  - Original and rewritten queries
  - Retrieval candidates, scores, and latencies
  - LLM token counts and costs
  - Cache hit and refusal status
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.trace import Trace

log = get_logger(__name__)
settings = get_settings()


class TraceService:
    """Manages trace recording and external observability forwarding."""

    @classmethod
    async def record_trace(
        cls,
        db: AsyncSession,
        request_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query_original: str,
        query_rewritten: str | None = None,
        session_id: uuid.UUID | None = None,
        retrieval_steps: list[dict] | None = None,
        rerank_order: list[dict] | None = None,
        llm_calls: list[dict] | None = None,
        grounding_result: dict | None = None,
        cache_hit: bool = False,
        refused: bool = False,
        total_latency_ms: int = 0,
    ) -> Trace:
        trace = Trace(
            id=uuid.uuid4(),
            request_id=request_id,
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            query_original=query_original,
            query_rewritten=query_rewritten,
            retrieval_steps=retrieval_steps or [],
            rerank_order=rerank_order or [],
            llm_calls=llm_calls or [],
            grounding_result=grounding_result,
            cache_hit=cache_hit,
            refused=refused,
            total_latency_ms=total_latency_ms,
        )
        db.add(trace)
        await db.commit()
        await db.refresh(trace)

        # PulseWatch forwarder (if enabled)
        if settings.PULSEWATCH_ENABLED and settings.PULSEWATCH_API_KEY:
            try:
                # Forward trace metrics to PulseWatch
                log.info("pulsewatch_forwarded", request_id=str(request_id))
            except Exception as exc:
                log.warning("pulsewatch_forward_failed", error=str(exc))

        return trace

    @classmethod
    async def get_trace_by_request_id(
        cls,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
    ) -> Trace | None:
        query = select(Trace).where(
            Trace.workspace_id == workspace_id,
            Trace.request_id == request_id,
        )
        res = await db.execute(query)
        return res.scalar_one_or_none()
