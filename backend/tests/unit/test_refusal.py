"""
tests/unit/test_refusal.py
──────────────────────────
Unit tests for confidence assessment and grounded refusal logic.
Pure unit tests — no database required.
"""
from __future__ import annotations

import uuid
from app.services.refusal_service import RefusalService, format_refusal_message
from app.services.retrieval_service import RetrievedChunk


def _make_candidate(score: float, content: str = "Test chunk content") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename="manual.pdf",
        workspace_id=uuid.uuid4(),
        page_number=1,
        section_title="Introduction",
        content=content,
        content_cleaned=content,
        final_score=score,
    )


def test_refusal_empty_candidates():
    query = "What is the return policy?"
    decision = RefusalService.evaluate(query, candidates=[], threshold=0.35)

    assert decision.refused is True
    assert decision.reason == "NO_RELEVANT_CHUNKS"
    assert decision.confidence_score == 0.0
    assert "No relevant documents were found" in (decision.refusal_message or "")
    assert query in (decision.refusal_message or "")


def test_refusal_low_confidence():
    query = "How to calibrate the flux capacitor?"
    candidates = [_make_candidate(score=0.15)]
    decision = RefusalService.evaluate(query, candidates=candidates, threshold=0.35)

    assert decision.refused is True
    assert decision.reason == "LOW_CONFIDENCE"
    assert decision.confidence_score == 0.15
    assert "The available documents do not contain sufficient evidence" in (decision.refusal_message or "")


def test_refusal_acceptable_confidence():
    query = "What are the working hours?"
    candidates = [_make_candidate(score=0.75), _make_candidate(score=0.40)]
    decision = RefusalService.evaluate(query, candidates=candidates, threshold=0.35)

    assert decision.refused is False
    assert decision.reason is None
    assert decision.refusal_message is None
    assert decision.confidence_score == 0.75


def test_refusal_custom_threshold():
    query = "Specific inquiry"
    candidates = [_make_candidate(score=0.45)]

    # With high threshold (0.50), score 0.45 should be refused
    decision_strict = RefusalService.evaluate(query, candidates=candidates, threshold=0.50)
    assert decision_strict.refused is True
    assert decision_strict.reason == "LOW_CONFIDENCE"

    # With lower threshold (0.40), score 0.45 should be accepted
    decision_lenient = RefusalService.evaluate(query, candidates=candidates, threshold=0.40)
    assert decision_lenient.refused is False


def test_refusal_message_formatting_truncation():
    long_query = "A" * 150
    msg = format_refusal_message(long_query, "LOW_CONFIDENCE")
    assert "..." in msg
    assert len(msg) < 300
