"""
app/services/ingestion_service.py
───────────────────────────────────
Core ingestion pipeline:
  parse → clean → chunk → embed → bulk-insert chunks
  + scanned-PDF detection
  + content-hash deduplication (replace stale chunks on re-upload)
  + optional PII redaction

Called by the RQ worker (synchronous) — SQLAlchemy sync session is used here
because RQ workers are sync processes. The service is pure Python; no FastAPI deps.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session  # sync session for worker

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RawChunk:
    chunk_index: int
    page_number: int | None
    section_title: str | None
    content: str


@dataclass
class ParsedDocument:
    chunks: list[RawChunk]
    page_count: int | None
    is_scanned: bool = False


# ── Content hash ──────────────────────────────────────────────────────────────

def compute_content_hash(data: bytes) -> str:
    """SHA-256 hex digest of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_pdf(data: bytes) -> ParsedDocument:
    """
    Parse a PDF using PyMuPDF (fitz).
    Detects scanned PDFs (zero extractable text on first 3 pages).
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    page_count = len(doc)

    # Scanned-PDF detection: sample first 3 pages
    sample_text = ""
    for i in range(min(3, page_count)):
        sample_text += doc[i].get_text("text")

    if page_count > 0 and not sample_text.strip():
        doc.close()
        return ParsedDocument(chunks=[], page_count=page_count, is_scanned=True)

    chunks: list[RawChunk] = []
    chunk_idx = 0
    current_section: str | None = None

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("blocks")  # returns list of (x0,y0,x1,y1,text,block_no,block_type)
        for block in blocks:
            if block[6] != 0:  # skip image blocks (type 1)
                continue
            text = block[4].strip()
            if not text:
                continue

            # Heuristic: short all-caps or bold-like lines are section headers
            if len(text) < 120 and (text.isupper() or text.endswith(":")):
                current_section = text

            chunks.append(RawChunk(
                chunk_index=chunk_idx,
                page_number=page_num,
                section_title=current_section,
                content=text,
            ))
            chunk_idx += 1

    doc.close()
    return ParsedDocument(chunks=chunks, page_count=page_count)


def parse_docx(data: bytes) -> ParsedDocument:
    """Parse a DOCX file using python-docx."""
    import io
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(data))
    chunks: list[RawChunk] = []
    chunk_idx = 0
    current_section: str | None = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # Headings become section markers
        if para.style.name.startswith("Heading"):
            current_section = text
        chunks.append(RawChunk(
            chunk_index=chunk_idx,
            page_number=None,  # DOCX doesn't expose page numbers easily
            section_title=current_section,
            content=text,
        ))
        chunk_idx += 1

    return ParsedDocument(chunks=chunks, page_count=None)


def parse_markdown(data: bytes) -> ParsedDocument:
    """Parse Markdown by splitting on headings."""
    from markdown_it import MarkdownIt
    md = MarkdownIt()
    tokens = md.parse(data.decode("utf-8", errors="replace"))

    chunks: list[RawChunk] = []
    chunk_idx = 0
    current_section: str | None = None
    current_text_parts: list[str] = []

    def flush():
        nonlocal chunk_idx
        text = "\n".join(current_text_parts).strip()
        if text:
            chunks.append(RawChunk(
                chunk_index=chunk_idx,
                page_number=None,
                section_title=current_section,
                content=text,
            ))
            chunk_idx += 1
        current_text_parts.clear()

    for token in tokens:
        if token.type == "heading_open":
            flush()
        elif token.type == "inline" and token.content:
            # Check if parent is heading
            current_text_parts.append(token.content)
        elif token.type == "heading_close":
            if current_text_parts:
                current_section = " ".join(current_text_parts).strip()
                current_text_parts.clear()

    flush()
    return ParsedDocument(chunks=chunks, page_count=None)


def parse_text(data: bytes) -> ParsedDocument:
    """Parse plain text by splitting on double newlines."""
    text = data.decode("utf-8", errors="replace")
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks = [
        RawChunk(chunk_index=i, page_number=None, section_title=None, content=p)
        for i, p in enumerate(paragraphs)
    ]
    return ParsedDocument(chunks=chunks, page_count=None)


PARSERS = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "md": parse_markdown,
    "txt": parse_text,
}


def parse_document(file_type: str, data: bytes) -> ParsedDocument:
    parser = PARSERS.get(file_type)
    if not parser:
        raise ValueError(f"Unsupported file type: {file_type}")
    return parser(data)


# ── Text cleaning ─────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Normalize unicode, strip control characters, collapse whitespace.
    Designed to be idempotent.
    """
    # Normalize to NFC
    text = unicodedata.normalize("NFC", text)
    # Remove control chars except tab/newline
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    # Collapse multiple spaces/tabs
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Structure-aware chunker ───────────────────────────────────────────────────

def split_into_chunks(
    raw_chunks: list[RawChunk],
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[RawChunk]:
    """
    Re-chunk the raw parser output into fixed-token-size windows with overlap.
    Uses a simple word-count approximation (1 token ≈ 0.75 words).
    Preserves page_number and section_title from the source block.
    """
    target_words = int(chunk_size * 0.75)
    overlap_words = int(overlap * 0.75)

    # Flatten all raw chunks into a sequence of (word, page, section) tuples
    words: list[tuple[str, int | None, str | None]] = []
    for rc in raw_chunks:
        page = rc.page_number
        section = rc.section_title
        for word in rc.content.split():
            words.append((word, page, section))

    if not words:
        return []

    result: list[RawChunk] = []
    idx = 0
    chunk_num = 0

    while idx < len(words):
        window = words[idx: idx + target_words]
        text = " ".join(w[0] for w in window)
        # Use metadata from the first word in the window
        page = window[0][1]
        section = window[0][2]

        result.append(RawChunk(
            chunk_index=chunk_num,
            page_number=page,
            section_title=section,
            content=text,
        ))
        chunk_num += 1

        # Advance by (target - overlap), so chunks overlap by overlap_words
        step = max(1, target_words - overlap_words)
        idx += step

    return result


# ── PII redaction (optional) ──────────────────────────────────────────────────

def redact_pii(text: str) -> str:
    """
    Optional: redact PII using Microsoft Presidio.
    Enabled only when PII_REDACT=true in config.
    Falls back to identity if presidio is not installed.
    """
    if not settings.PII_REDACT:
        return text
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()
        results = analyzer.analyze(text=text, language="en")
        return anonymizer.anonymize(text=text, analyzer_results=results).text
    except ImportError:
        log.warning("presidio_not_installed", msg="PII_REDACT=true but presidio not installed; skipping")
        return text
    except Exception as exc:
        log.warning("pii_redact_error", error=str(exc))
        return text


# ── Embedder ──────────────────────────────────────────────────────────────────

_embedder = None


def get_embedder():
    """Lazy-load the sentence-transformers model (cached in process)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        log.info("embedder_loaded", model=settings.EMBEDDING_MODEL)
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed texts. Returns list of float vectors."""
    model = get_embedder()
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


# ── Main ingestion pipeline (sync, called by RQ worker) ──────────────────────

def ingest_document(
    db: Session,
    document_id: uuid.UUID,
    file_data: bytes,
    file_type: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> None:
    """
    Full ingestion pipeline for one document.
    Updates document status throughout; writes chunks on success.
    """
    from app.models.document import Document
    from app.models.chunk import Chunk

    chunk_size = chunk_size or settings.EMBEDDING_DIM  # use 512 words by default
    overlap = overlap or 64
    _chunk_size_tokens = 512  # word-based approximation
    _overlap_tokens = overlap

    # ── 1. Mark as processing ─────────────────────────────────────────────────
    db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status="processing")
    )
    db.commit()

    try:
        doc: Document | None = db.get(Document, document_id)
        if not doc:
            log.error("document_not_found", document_id=str(document_id))
            return

        workspace_id = doc.workspace_id

        # ── 2. Parse ──────────────────────────────────────────────────────────
        log.info("parsing", document_id=str(document_id), file_type=file_type)
        parsed = parse_document(file_type, file_data)

        if parsed.is_scanned:
            db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status="scanned_pdf",
                    error_message=(
                        "This appears to be a scanned PDF with no extractable text. "
                        "OCR is not supported in this version. Please upload a text-based PDF."
                    ),
                )
            )
            db.commit()
            log.warning("scanned_pdf_detected", document_id=str(document_id))
            return

        if not parsed.chunks:
            db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", error_message="Document appears to be empty.")
            )
            db.commit()
            return

        # ── 3. Re-chunk with overlap ──────────────────────────────────────────
        log.info("chunking", document_id=str(document_id), raw_blocks=len(parsed.chunks))
        final_chunks = split_into_chunks(parsed.chunks, chunk_size=_chunk_size_tokens, overlap=_overlap_tokens)

        # ── 4. Clean + PII redact ──────────────────────────────────────────────
        for rc in final_chunks:
            rc.content = clean_text(rc.content)

        cleaned_texts = [redact_pii(rc.content) for rc in final_chunks]

        # Filter truly empty chunks
        pairs = [(rc, ct) for rc, ct in zip(final_chunks, cleaned_texts) if ct.strip()]
        if not pairs:
            db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", error_message="All chunks were empty after cleaning.")
            )
            db.commit()
            return

        final_chunks, cleaned_texts = zip(*pairs)  # type: ignore[assignment]

        # ── 5. Delete old chunks (re-ingest flow) ──────────────────────────────
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.flush()

        # ── 6. Embed ──────────────────────────────────────────────────────────
        log.info("embedding", document_id=str(document_id), num_chunks=len(cleaned_texts))
        embeddings = embed_texts(list(cleaned_texts))

        # ── 7. Bulk insert chunks ──────────────────────────────────────────────
        chunk_objs = []
        for rc, cleaned, emb in zip(final_chunks, cleaned_texts, embeddings):
            chunk_objs.append(Chunk(
                document_id=document_id,
                workspace_id=workspace_id,
                chunk_index=rc.chunk_index,
                page_number=rc.page_number,
                section_title=rc.section_title,
                content=rc.content,
                content_cleaned=cleaned,
                token_count=len(cleaned.split()),
                embedding=emb,
                metadata_json={},
            ))

        db.bulk_save_objects(chunk_objs)

        # ── 8. Mark ready ──────────────────────────────────────────────────────
        db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status="ready",
                page_count=parsed.page_count,
                chunk_count=len(chunk_objs),
                error_message=None,
            )
        )
        db.commit()
        log.info("ingestion_complete", document_id=str(document_id), chunks=len(chunk_objs))

    except Exception as exc:
        db.rollback()
        db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="failed", error_message=str(exc)[:512])
        )
        db.commit()
        log.exception("ingestion_failed", document_id=str(document_id), error=str(exc))
        raise
