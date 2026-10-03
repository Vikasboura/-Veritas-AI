"""
tests/unit/test_cache_isolation.py
───────────────────────────────────
Unit and tenant-isolation tests for SemanticCache:
  - Cache hits on exact normalized question
  - Semantic vector similarity cache hits
  - Strict tenant isolation: Workspace B NEVER receives cached answers from Workspace A
  - Cache TTL expiration
  - Workspace invalidation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic_cache import SemanticCache
from app.services.cache_service import CacheService, normalize_question, hash_question
from app.services.ingestion_service import get_embedder


def test_question_normalization():
    q1 = "  What is the company's VACATION policy???  "
    q2 = "what is the companys vacation policy"
    assert normalize_question(q1) == normalize_question(q2)
    assert hash_question(q1) == hash_question(q2)


@pytest.mark.asyncio
async def test_cache_exact_hit(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    question = "What are the remote work guidelines?"
    answer = {"answer": "Remote work is permitted on Tuesdays and Thursdays.", "citations": []}

    await CacheService.set_cached_answer(db_session, ws_id, question, answer, ttl_seconds=3600)

    # Lookup with exact question
    cached = await CacheService.get_cached_answer(db_session, ws_id, question)
    assert cached is not None
    assert cached["answer"] == answer["answer"]


@pytest.mark.asyncio
async def test_cache_tenant_isolation(db_session: AsyncSession):
    """
    CRITICAL SECURITY INVARIANT:
    Tenant A's cached proprietary answers must NEVER be returned to Tenant B,
    even when Tenant B asks the exact same question.
    """
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()

    question = "What is the secret merger valuation?"
    secret_answer_a = {"answer": "Target acquisition price is $4.2B.", "citations": []}

    # Store in Workspace A
    await CacheService.set_cached_answer(db_session, ws_a, question, secret_answer_a, ttl_seconds=3600)

    # Workspace A gets the answer
    cached_a = await CacheService.get_cached_answer(db_session, ws_a, question)
    assert cached_a is not None
    assert cached_a["answer"] == secret_answer_a["answer"]

    # Workspace B MUST get None (cache miss)
    cached_b = await CacheService.get_cached_answer(db_session, ws_b, question)
    assert cached_b is None


@pytest.mark.asyncio
async def test_cache_ttl_expiration(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    question = "What is the daily per diem?"
    answer = {"answer": "The daily per diem is $75.", "citations": []}

    # Insert an already expired entry
    q_hash = hash_question(question)
    embedder = get_embedder()
    q_vec = embedder.encode(question, normalize_embeddings=True).tolist()

    expired_entry = SemanticCache(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        question_hash=q_hash,
        question_emb=q_vec,
        answer_json=answer,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(expired_entry)
    await db_session.commit()

    # Should be a cache miss
    cached = await CacheService.get_cached_answer(db_session, ws_id, question)
    assert cached is None


@pytest.mark.asyncio
async def test_cache_workspace_invalidation(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    ws_other = uuid.uuid4()

    await CacheService.set_cached_answer(db_session, ws_id, "Question 1", {"answer": "A1"}, ttl_seconds=3600)
    await CacheService.set_cached_answer(db_session, ws_id, "Question 2", {"answer": "A2"}, ttl_seconds=3600)
    await CacheService.set_cached_answer(db_session, ws_other, "Question 3", {"answer": "A3"}, ttl_seconds=3600)

    # Invalidate ws_id
    deleted = await CacheService.invalidate_workspace(db_session, ws_id)
    assert deleted == 2

    # ws_id entries gone
    assert await CacheService.get_cached_answer(db_session, ws_id, "Question 1") is None
    # ws_other entries untouched
    assert await CacheService.get_cached_answer(db_session, ws_other, "Question 3") is not None
