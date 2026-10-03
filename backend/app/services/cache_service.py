"""
app/services/cache_service.py
───────────────────────────────
Semantic cache with strict per-workspace isolation.
Ensures answers to identical or semantically identical questions within the
same workspace are returned instantly, while completely preventing cross-tenant leakage.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.semantic_cache import SemanticCache
from app.services.ingestion_service import get_embedder

log = get_logger(__name__)
settings = get_settings()


def normalize_question(q: str) -> str:
    """Normalize question text: lowercase, remove excess whitespace and non-alphanumeric chars."""
    text = q.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text)


def hash_question(q: str) -> str:
    return hashlib.sha256(normalize_question(q).encode("utf-8")).hexdigest()


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class CacheService:
    """Per-workspace semantic cache manager."""

    @classmethod
    async def get_cached_answer(
        cls,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        question: str,
        threshold: float | None = None,
    ) -> dict | None:
        """
        Check for an existing cached answer.
        First checks exact normalized hash, then checks semantic vector similarity.
        CRITICAL: ONLY searches within workspace_id!
        """
        now = datetime.now(timezone.utc)
        sim_threshold = threshold or settings.CACHE_SIMILARITY_THRESHOLD
        q_hash = hash_question(question)

        # 1. Exact match check
        exact_query = select(SemanticCache).where(
            and_(
                SemanticCache.workspace_id == workspace_id,
                SemanticCache.question_hash == q_hash,
                SemanticCache.expires_at > now,
            )
        )
        res = await db.execute(exact_query)
        exact_hit = res.scalar_one_or_none()
        if exact_hit:
            log.info("semantic_cache_exact_hit", workspace_id=str(workspace_id), hash=q_hash)
            return exact_hit.answer_json

        # 2. Semantic ANN similarity check
        embedder = get_embedder()
        q_vector = embedder.encode(question, normalize_embeddings=True).tolist()

        active_query = select(SemanticCache).where(
            and_(
                SemanticCache.workspace_id == workspace_id,
                SemanticCache.expires_at > now,
            )
        )
        res_active = await db.execute(active_query)
        candidates = res_active.scalars().all()

        best_score = -1.0
        best_hit: SemanticCache | None = None

        for cand in candidates:
            if cand.question_emb:
                sim = _cosine_similarity(q_vector, cand.question_emb)
                if sim > best_score:
                    best_score = sim
                    best_hit = cand

        if best_hit and best_score >= sim_threshold:
            log.info(
                "semantic_cache_ann_hit",
                workspace_id=str(workspace_id),
                similarity=round(best_score, 4),
                threshold=sim_threshold,
            )
            return best_hit.answer_json

        return None

    @classmethod
    async def set_cached_answer(
        cls,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        question: str,
        answer_json: dict,
        ttl_seconds: int | None = None,
    ) -> SemanticCache:
        """Cache an answer for a workspace with a TTL."""
        ttl = ttl_seconds or settings.CACHE_TTL_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        q_hash = hash_question(question)

        embedder = get_embedder()
        q_vector = embedder.encode(question, normalize_embeddings=True).tolist()

        cache_entry = SemanticCache(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            question_hash=q_hash,
            question_emb=q_vector,
            answer_json=answer_json,
            expires_at=expires_at,
        )
        db.add(cache_entry)
        await db.commit()
        await db.refresh(cache_entry)
        return cache_entry

    @classmethod
    async def invalidate_workspace(
        cls,
        db: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> int:
        """Purge all cached entries for a workspace upon document ingestion or deletion."""
        query = delete(SemanticCache).where(SemanticCache.workspace_id == workspace_id)
        res = await db.execute(query)
        await db.commit()
        return res.rowcount or 0
