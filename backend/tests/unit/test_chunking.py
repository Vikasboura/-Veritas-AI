"""
tests/unit/test_chunking.py
────────────────────────────
Tests for the chunking and text-cleaning logic.
No DB, no embeddings — pure unit tests.
"""
from __future__ import annotations

import pytest

from app.services.ingestion_service import (
    RawChunk,
    clean_text,
    split_into_chunks,
    parse_text,
    parse_markdown,
)


# ── clean_text ────────────────────────────────────────────────────────────────

def test_clean_text_strips_control_chars():
    dirty = "Hello\x00World\x07!"
    result = clean_text(dirty)
    assert "\x00" not in result
    assert "\x07" not in result
    assert "Hello" in result
    assert "World" in result


def test_clean_text_collapses_whitespace():
    text = "word1   word2\t\tword3"
    result = clean_text(text)
    assert "  " not in result
    assert result == "word1 word2 word3"


def test_clean_text_collapses_excess_newlines():
    text = "para1\n\n\n\n\npara2"
    result = clean_text(text)
    assert result.count("\n") <= 2


def test_clean_text_idempotent():
    text = "  Hello  World  "
    assert clean_text(clean_text(text)) == clean_text(text)


# ── split_into_chunks ──────────────────────────────────────────────────────────

def _make_raw(content: str, idx: int = 0) -> RawChunk:
    return RawChunk(chunk_index=idx, page_number=1, section_title="Test", content=content)


def test_chunker_produces_chunks():
    # 200 words of text → should produce at least 1 chunk
    words = " ".join([f"word{i}" for i in range(200)])
    raw = [_make_raw(words)]
    chunks = split_into_chunks(raw, chunk_size=128, overlap=16)
    assert len(chunks) >= 1


def test_chunker_respects_size():
    # With chunk_size=64, each chunk should be ≤ ~50 words (0.75 factor)
    words = " ".join([f"word{i}" for i in range(500)])
    raw = [_make_raw(words)]
    chunks = split_into_chunks(raw, chunk_size=64, overlap=0)
    target_words = int(64 * 0.75)
    for c in chunks[:-1]:  # last chunk may be smaller
        assert len(c.content.split()) <= target_words + 5  # allow small rounding


def test_chunker_overlap():
    """With overlap > 0, chunks should share some words."""
    words = " ".join([f"w{i}" for i in range(200)])
    raw = [_make_raw(words)]

    chunks_no_overlap = split_into_chunks(raw, chunk_size=64, overlap=0)
    chunks_with_overlap = split_into_chunks(raw, chunk_size=64, overlap=16)

    # Overlapping chunker should produce more chunks from the same text
    assert len(chunks_with_overlap) >= len(chunks_no_overlap)


def test_chunker_empty_input():
    chunks = split_into_chunks([], chunk_size=512, overlap=64)
    assert chunks == []


def test_chunker_single_word():
    raw = [_make_raw("hello")]
    chunks = split_into_chunks(raw, chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert "hello" in chunks[0].content


def test_chunker_preserves_page_number():
    raw = [
        RawChunk(chunk_index=0, page_number=3, section_title="S1", content="word " * 100),
    ]
    chunks = split_into_chunks(raw, chunk_size=64, overlap=0)
    assert all(c.page_number == 3 for c in chunks)


# ── parse_text ────────────────────────────────────────────────────────────────

def test_parse_text_splits_paragraphs():
    content = b"Paragraph one.\n\nParagraph two.\n\nParagraph three."
    parsed = parse_text(content)
    assert len(parsed.chunks) == 3
    assert parsed.chunks[0].content == "Paragraph one."
    assert parsed.chunks[1].content == "Paragraph two."


def test_parse_text_empty():
    parsed = parse_text(b"")
    assert parsed.chunks == []


def test_parse_text_single_paragraph():
    parsed = parse_text(b"Only one paragraph here.")
    assert len(parsed.chunks) == 1


# ── parse_markdown ────────────────────────────────────────────────────────────

def test_parse_markdown_basic():
    md = b"# Title\n\nSome body text here.\n\n## Section\n\nMore content."
    parsed = parse_markdown(md)
    assert len(parsed.chunks) >= 1
    assert parsed.page_count is None  # Markdown has no pages


def test_parse_markdown_empty():
    parsed = parse_markdown(b"")
    assert parsed.chunks == []
