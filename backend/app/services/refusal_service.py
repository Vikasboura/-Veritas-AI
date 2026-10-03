"""
app/services/refusal_service.py
─────────────────────────────────
Confidence assessment and refusal logic.
Strictly prevents hallucinations by refusing to answer when retrieved context
is insufficient or confidence falls below the configured threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.retrieval_service import RetrievedChunk

log = get_logger(__name__)
settings = get_settings()


@dataclass
class RefusalDecision:
    refused: bool
    reason: str | None = None
    confidence_score: float = 0.0
    threshold: float = 0.0
    refusal_message: str | None = None


def format_refusal_message(query: str, reason: str = "NO_RELEVANT_CHUNKS") -> str:
    """Standardized grounded refusal message."""
    clean_query = query.strip()
    if len(clean_query) > 100:
        clean_query = clean_query[:97] + "..."

    if reason == "NO_RELEVANT_CHUNKS":
        return (
            f"I cannot answer this question based on the documents in this workspace. "
            f"No relevant documents were found that match your inquiry: \"{clean_query}\"."
        )
    return (
        f"I cannot answer this question based on the documents in this workspace. "
        f"The available documents do not contain sufficient evidence to answer: \"{clean_query}\"."
    )


class RefusalService:
    """Evaluates candidate chunks to determine if the query must be refused."""

    @staticmethod
    def evaluate(
        query: str,
        candidates: Sequence[RetrievedChunk],
        threshold: float | None = None,
    ) -> RefusalDecision:
        """
        Evaluate retrieved candidates against the confidence threshold.

        Rules:
          1. If candidates is empty -> REFUSE (NO_RELEVANT_CHUNKS)
          2. If top candidate final_score < threshold -> REFUSE (LOW_CONFIDENCE)
          3. Otherwise -> ACCEPT (proceed to generation)
        """
        conf_threshold = threshold if threshold is not None else settings.REFUSAL_CONFIDENCE_THRESHOLD

        if not candidates:
            log.info("query_refused_no_candidates", query=query)
            return RefusalDecision(
                refused=True,
                reason="NO_RELEVANT_CHUNKS",
                confidence_score=0.0,
                threshold=conf_threshold,
                refusal_message=format_refusal_message(query, reason="NO_RELEVANT_CHUNKS"),
            )

        top_score = candidates[0].final_score

        if top_score < conf_threshold:
            log.info(
                "query_refused_low_confidence",
                query=query,
                score=top_score,
                threshold=conf_threshold,
            )
            return RefusalDecision(
                refused=True,
                reason="LOW_CONFIDENCE",
                confidence_score=top_score,
                threshold=conf_threshold,
                refusal_message=format_refusal_message(query, reason="LOW_CONFIDENCE"),
            )

        return RefusalDecision(
            refused=False,
            reason=None,
            confidence_score=top_score,
            threshold=conf_threshold,
            refusal_message=None,
        )
