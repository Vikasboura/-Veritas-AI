"""
app/services/query_service.py
──────────────────────────────
Query understanding, rewrite, decomposition, and routing.
Optimizes user inquiries before retrieval.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.llm_client import LLMClient, get_llm_client

log = get_logger(__name__)

REWRITE_PROMPT = """You are a retrieval query optimizer for a RAG system.
Given a user query and optional chat history, rewrite the user query into a clean, standalone search query that maximizes recall across enterprise documents.
- Resolve any pronouns (it, that, they) based on context.
- Strip conversational filler (e.g. "can you tell me", "please search for").
- Output ONLY the rewritten search query, nothing else.

User Query: {query}
Rewritten Query:"""

DECOMPOSE_PROMPT = """Analyze the following user query. If it asks multiple distinct questions, split it into up to 3 individual sub-queries.
If it is a single question, return just that question.
Output your result as a JSON array of strings, e.g. ["sub-query 1", "sub-query 2"].

User Query: {query}
JSON Output:"""


@dataclass
class RoutedQuery:
    original_query: str
    rewritten_query: str
    sub_queries: list[str]
    intent: str  # "retrieve", "greeting", "unsupported"


class QueryService:
    """Orchestrates query rewriting, sub-query decomposition, and intent routing."""

    @classmethod
    async def rewrite_query(
        cls,
        query: str,
        llm: LLMClient | None = None,
    ) -> str:
        """Rewrite raw conversational query into a targeted search query."""
        clean_q = query.strip()
        # Fast path for very short or keyword-like queries
        if len(clean_q.split()) <= 4:
            return clean_q

        client = llm or get_llm_client()
        prompt = REWRITE_PROMPT.format(query=clean_q)
        try:
            rewritten, _ = await client.create_chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=64,
            )
            clean_rewritten = rewritten.strip().strip('"')
            return clean_rewritten if clean_rewritten else clean_q
        except Exception as exc:
            log.warning("query_rewrite_failed", error=str(exc))
            return clean_q

    @classmethod
    async def decompose_query(
        cls,
        query: str,
        llm: LLMClient | None = None,
    ) -> list[str]:
        """Decompose compound questions into sub-queries."""
        clean_q = query.strip()
        if " and " not in clean_q.lower() and "?" not in clean_q[:-1]:
            return [clean_q]

        client = llm or get_llm_client()
        prompt = DECOMPOSE_PROMPT.format(query=clean_q)
        try:
            resp, _ = await client.create_chat_completion(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=128,
            )
            # Parse JSON
            raw = resp.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").replace("json", "").strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                return [str(q).strip() for q in parsed if str(q).strip()]
        except Exception as exc:
            log.warning("query_decompose_failed", error=str(exc))

        return [clean_q]

    @classmethod
    async def process_and_route(
        cls,
        query: str,
        llm: LLMClient | None = None,
    ) -> RoutedQuery:
        """Full pipeline: route intent, rewrite, decompose."""
        clean_q = query.strip().lower()
        if clean_q in {"hi", "hello", "hey", "help", "good morning", "good evening"}:
            return RoutedQuery(
                original_query=query,
                rewritten_query=query,
                sub_queries=[query],
                intent="greeting",
            )

        rewritten = await cls.rewrite_query(query, llm=llm)
        sub_queries = await cls.decompose_query(rewritten, llm=llm)

        return RoutedQuery(
            original_query=query,
            rewritten_query=rewritten,
            sub_queries=sub_queries,
            intent="retrieve",
        )
