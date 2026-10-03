"""
app/services/document_service.py
──────────────────────────────────
Document upload, listing, deletion.
Enqueues the ingestion RQ job after saving the document record.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.chunk import Chunk
from app.schemas.document import DocumentResponse, DocumentUploadResponse

log = get_logger(__name__)
settings = get_settings()

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/markdown": "md",
    "text/plain": "txt",
}

EXT_TO_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
}


class DocumentError(Exception):
    pass


class DocumentTooLargeError(DocumentError):
    pass


class UnsupportedFileTypeError(DocumentError):
    pass


def _detect_file_type(filename: str, content_type: str | None) -> str:
    """
    Determine file type from extension first, then content-type fallback.
    Raises UnsupportedFileTypeError for disallowed types.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in EXT_TO_TYPE:
        ft = EXT_TO_TYPE[suffix]
    elif content_type and content_type in ALLOWED_MIME_TYPES:
        ft = ALLOWED_MIME_TYPES[content_type]
    else:
        allowed = ", ".join(settings.allowed_extensions_set)
        raise UnsupportedFileTypeError(
            f"File type '{suffix or content_type}' not allowed. Accepted: {allowed}"
        )
    if ft not in settings.allowed_extensions_set:
        raise UnsupportedFileTypeError(f"Extension '{ft}' is not in the allowed list.")
    return ft


async def upload_document(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    uploader_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    file_data: bytes,
) -> tuple[Document, bool]:
    """
    Validate, dedup, and create the Document row.
    Returns (document, is_new). Caller enqueues the ingestion job.
    is_new=False means the file was identical — no re-ingestion needed.
    """
    # ── Size check ────────────────────────────────────────────────────────────
    if len(file_data) > settings.max_upload_size_bytes:
        raise DocumentTooLargeError(
            f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit."
        )

    # ── Type check ────────────────────────────────────────────────────────────
    file_type = _detect_file_type(filename, content_type)

    # ── Content-hash dedup ───────────────────────────────────────────────────
    content_hash = hashlib.sha256(file_data).hexdigest()

    result = await db.execute(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.content_hash == content_hash,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == "ready":
            # Identical file already ingested — skip silently
            log.info("document_duplicate_skip", document_id=str(existing.id))
            return existing, False
        # Same hash but not ready (failed/pending) — reset and re-ingest
        existing.status = "pending"
        existing.error_message = None
        await db.commit()
        log.info("document_reingest_reset", document_id=str(existing.id))
        return existing, True

    # ── New document ──────────────────────────────────────────────────────────
    doc = Document(
        workspace_id=workspace_id,
        uploaded_by=uploader_id,
        filename=filename,
        content_hash=content_hash,
        file_type=file_type,
        file_size_bytes=len(file_data),
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    log.info("document_created", document_id=str(doc.id), filename=filename)
    return doc, True


async def list_documents(
    db: AsyncSession, workspace_id: uuid.UUID
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document_or_404(
    db: AsyncSession, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise DocumentError(f"Document {document_id} not found in this workspace.")
    return doc


async def delete_document(
    db: AsyncSession, workspace_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    doc = await get_document_or_404(db, workspace_id, document_id)
    await db.delete(doc)
    await db.commit()
    log.info("document_deleted", document_id=str(document_id))


def enqueue_ingestion(document_id: uuid.UUID, file_data: bytes, file_type: str) -> str:
    """
    Push the ingestion job onto the RQ 'ingestion' queue.
    Returns the job ID.
    """
    import redis
    from rq import Queue
    from app.workers.ingestion_worker import run_ingestion

    conn = redis.from_url(settings.REDIS_URL)
    q = Queue("ingestion", connection=conn)
    job = q.enqueue(
        run_ingestion,
        args=(str(document_id), file_data, file_type),
        job_timeout=600,  # 10 minutes max per doc
    )
    log.info("job_enqueued", document_id=str(document_id), job_id=job.id)
    return job.id
