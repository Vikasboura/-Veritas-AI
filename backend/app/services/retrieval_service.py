"""
app/services/retrieval_service.py
───────────────────────────────────
Hybrid retrieval pipeline:
  1. Dense vector search (pgvector cosine distance)
  2. Full-text search (Postgres tsvector ts_rank_cd)
  3. Reciprocal Rank Fusion (RRF) with constant k=60
  4. Cross-Encoder reranking (ms-marco-MiniLM-L-6-v2)
  5. Strict tenant isolation (WHERE workspace_id = :workspace_id)
  6. Document readiness filter (Document.status == 'ready')
  7. Optional document filter (doc_ids)

Includes pure RRF implementation and SQLite-compatible fallback for unit/integration tests.
"""
from __future__ import annotations

import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
import math
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.document import Document
from app.schemas.chat import Citation
from app.services.ingestion_service import get_embedder

log = get_logger(__name__)
settings = get_settings()


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    workspace_id: uuid.UUID
    page_number: int | None
    section_title: str | None
    content: str
    content_cleaned: str
    vector_rank: int | None = None
    fts_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    final_score: float = 0.0

    def to_citation(self) -> Citation:
        return Citation(
            chunk_id=self.chunk_id,
            doc_id=self.document_id,
            doc_filename=self.document_filename,
            page_number=self.page_number,
            chunk_text=self.content,
            score=round(self.final_score, 4),
        )


# ── Pure RRF (Reciprocal Rank Fusion) ─────────────────────────────────────────

def compute_rrf(
    ranked_lists: Sequence[Sequence[Any]],
    k: int = 60,
) -> list[tuple[Any, float]]:
    """
    Pure Reciprocal Rank Fusion (RRF).
    Formula: RRF(d) = sum_{r in R} 1 / (k + rank_r(d))
    where rank_r(d) is 1-indexed rank of item d in ranked list r.

    Args:
        ranked_lists: Sequence of ordered sequences (each item uniquely identifiable).
        k: Smoothing constant (default 60, per Cormack et al. 2009).

    Returns:
        List of (item, rrf_score) tuples sorted by rrf_score descending.
    """
    scores: dict[Any, float] = {}

    for ranked_list in ranked_lists:
        for rank_0, item in enumerate(ranked_list):
            rank = rank_0 + 1  # 1-indexed
            scores[item] = scores.get(item, 0.0) + (1.0 / (k + rank))

    # Sort descending by score; break ties deterministically by str(item)
    sorted_items = sorted(
        scores.items(),
        key=lambda x: (x[1], -len(str(x[0]))),
        reverse=True,
    )
    return sorted_items


# ── Reranker Lazy Loader ──────────────────────────────────────────────────────

_reranker = None


def get_reranker():
    """Lazy load the cross-encoder reranker model."""
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(settings.RERANKER_MODEL)
            log.info("reranker_loaded", model=settings.RERANKER_MODEL)
        except Exception as exc:
            log.warning("reranker_load_failed", error=str(exc))
            _reranker = None
    return _reranker


# ── Vector and FTS search helpers ─────────────────────────────────────────────

def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def _search_vector(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query_vector: list[float],
    top_k: int,
    doc_ids: list[uuid.UUID] | None = None,
) -> list[Chunk]:
    """Execute vector search scoped strictly to workspace_id and ready documents."""
    dialect_name = db.bind.dialect.name if db.bind else "sqlite"

    conditions = [
        Chunk.workspace_id == workspace_id,
        Document.status == "ready",
    ]
    if doc_ids:
        conditions.append(Chunk.document_id.in_(doc_ids))

    if dialect_name == "postgresql":
        # pgvector cosine distance
        query = (
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .options(selectinload(Chunk.document))
            .where(and_(*conditions))
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(top_k)
        )
        res = await db.execute(query)
        return list(res.scalars().all())

    # Fallback for SQLite / test environments
    query = (
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .options(selectinload(Chunk.document))
        .where(and_(*conditions))
    )
    res = await db.execute(query)
    chunks = list(res.scalars().all())

    # Score in Python
    scored_chunks: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        emb = chunk.embedding
        if emb:
            sim = _cosine_similarity(query_vector, emb)
            scored_chunks.append((sim, chunk))
        else:
            scored_chunks.append((-1.0, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


async def _search_fts(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query_text: str,
    top_k: int,
    doc_ids: list[uuid.UUID] | None = None,
) -> list[Chunk]:
    """Execute full-text search scoped strictly to workspace_id and ready documents."""
    dialect_name = db.bind.dialect.name if db.bind else "sqlite"

    conditions = [
        Chunk.workspace_id == workspace_id,
        Document.status == "ready",
    ]
    if doc_ids:
        conditions.append(Chunk.document_id.in_(doc_ids))

    if dialect_name == "postgresql":
        tsquery = func.plainto_tsquery("english", query_text)
        query = (
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .options(selectinload(Chunk.document))
            .where(
                and_(
                    *conditions,
                    func.to_tsvector("english", Chunk.content_cleaned).op("@@")(tsquery),
                )
            )
            .order_by(func.ts_rank_cd(func.to_tsvector("english", Chunk.content_cleaned), tsquery).desc())
            .limit(top_k)
        )
        res = await db.execute(query)
        return list(res.scalars().all())

    # Fallback for SQLite / test environments: simple keyword match ranking
    query = (
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .options(selectinload(Chunk.document))
        .where(and_(*conditions))
    )
    res = await db.execute(query)
    chunks = list(res.scalars().all())

    keywords = [kw.lower() for kw in query_text.split() if len(kw) > 1]
    if not keywords:
        return chunks[:top_k]

    scored_chunks: list[tuple[int, Chunk]] = []
    for chunk in chunks:
        text = (chunk.content_cleaned or "").lower()
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


# ── Retrieval Service ─────────────────────────────────────────────────────────

class RetrievalService:
    """Orchestrates hybrid retrieval, reciprocal rank fusion, and cross-encoder reranking."""

    @staticmethod
    async def retrieve(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        query: str,
        top_k_vector: int | None = None,
        top_k_fts: int | None = None,
        top_n_rerank: int | None = None,
        doc_ids: list[uuid.UUID] | None = None,
        rerank: bool | None = None,
    ) -> list[RetrievedChunk]:
        """
        Main retrieval entrypoint.
        Executes vector search + FTS search, fuses via RRF, optionally reranks with cross-encoder.
        Guarantees:
          - Only returns chunks matching workspace_id.
          - Only returns chunks from documents with status == 'ready'.
        """
        top_k_vec = top_k_vector or settings.RETRIEVAL_TOP_K_VECTOR
        top_k_kw = top_k_fts or settings.RETRIEVAL_TOP_K_FTS
        top_n = top_n_rerank or settings.RETRIEVAL_TOP_N_RERANK
        should_rerank = settings.RERANKER_ENABLED if rerank is None else rerank

        # 1. Embed the query
        embedder = get_embedder()
        query_vector = embedder.encode(query, normalize_embeddings=True).tolist()

        # 2. Run vector and FTS searches
        vector_chunks: list[Chunk] = []
        fts_chunks: list[Chunk] = []

        try:
            vector_chunks = await _search_vector(
                db=db,
                workspace_id=workspace_id,
                query_vector=query_vector,
                top_k=top_k_vec,
                doc_ids=doc_ids,
            )
        except Exception as exc:
            log.warning("vector_search_failed", error=str(exc))

        if settings.HYBRID_ENABLED:
            try:
                fts_chunks = await _search_fts(
                    db=db,
                    workspace_id=workspace_id,
                    query_text=query,
                    top_k=top_k_kw,
                    doc_ids=doc_ids,
                )
            except Exception as exc:
                log.warning("fts_search_failed", error=str(exc))

        # 3. Build candidate lookup map
        chunk_map: dict[uuid.UUID, Chunk] = {}
        for c in vector_chunks:
            chunk_map[c.id] = c
        for c in fts_chunks:
            chunk_map[c.id] = c

        if not chunk_map:
            log.info("retrieval_empty", query=query, workspace_id=str(workspace_id))
            return []

        # 4. Reciprocal Rank Fusion (RRF)
        vec_ids = [c.id for c in vector_chunks]
        fts_ids = [c.id for c in fts_chunks]

        rrf_results = compute_rrf(
            ranked_lists=[vec_ids, fts_ids],
            k=settings.RETRIEVAL_RRF_K,
        )

        candidates: list[RetrievedChunk] = []
        vec_rank_map = {cid: idx + 1 for idx, cid in enumerate(vec_ids)}
        fts_rank_map = {cid: idx + 1 for idx, cid in enumerate(fts_ids)}

        max_possible_rrf = 2.0 / (settings.RETRIEVAL_RRF_K + 1)
        for cid, rrf_score in rrf_results:
            chunk = chunk_map[cid]
            normalized_score = min(1.0, rrf_score / max_possible_rrf) if max_possible_rrf > 0 else rrf_score
            candidates.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_filename=chunk.document.filename if chunk.document else "unknown",
                    workspace_id=chunk.workspace_id,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    content=chunk.content,
                    content_cleaned=chunk.content_cleaned,
                    vector_rank=vec_rank_map.get(cid),
                    fts_rank=fts_rank_map.get(cid),
                    rrf_score=rrf_score,
                    final_score=normalized_score,
                )
            )

        # 5. Cross-Encoder Reranking (optional)
        if should_rerank and candidates:
            reranker = get_reranker()
            if reranker is not None:
                try:
                    pairs = [[query, cand.content_cleaned] for cand in candidates]
                    scores = reranker.predict(pairs)
                    for cand, score in zip(candidates, scores):
                        cand.rerank_score = float(score)
                        cand.final_score = float(score)

                    candidates.sort(key=lambda x: x.final_score, reverse=True)
                except Exception as exc:
                    log.warning("reranking_execution_failed", error=str(exc))

        # Return top N candidates
        return candidates[:top_n]
