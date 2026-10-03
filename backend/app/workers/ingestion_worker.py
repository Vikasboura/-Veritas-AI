"""
app/workers/ingestion_worker.py
────────────────────────────────
RQ job entrypoint for document ingestion.
Uses a sync SQLAlchemy session (psycopg2) because RQ workers are sync.
"""
from __future__ import annotations

import uuid

from app.core.config import get_settings
from app.core.logging import get_logger, configure_logging

log = get_logger(__name__)
settings = get_settings()


def _mark_doc_failed(doc_uuid: uuid.UUID, error_msg: str) -> None:
    """Fail-safe helper to update document status if worker encounters an unhandled exception."""
    try:
        import asyncio
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import update
        from app.models.document import Document

        async def _update():
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Document)
                    .where(Document.id == doc_uuid)
                    .values(status="failed", error_message=error_msg[:512])
                )
                await session.commit()

        asyncio.run(_update())
    except Exception as e:
        log.error("failed_to_mark_doc_failed", error=str(e), doc_id=str(doc_uuid))


def get_sync_db():
    """Create a synchronous SQLAlchemy session for the worker process."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def run_ingestion(document_id: str, file_data: bytes, file_type: str) -> None:
    """
    RQ job / background task: ingest a single document.
    Args are primitive types (serializable by RQ/Redis).
    """
    configure_logging()
    doc_uuid = uuid.UUID(document_id)
    log.info("worker_ingestion_start", document_id=document_id, file_type=file_type)

    try:
        db = get_sync_db()
    except Exception as exc:
        log.exception("worker_get_db_failed", document_id=document_id, error=str(exc))
        _mark_doc_failed(doc_uuid, f"Database connection error in ingestion worker: {exc}")
        return

    try:
        from app.services.ingestion_service import ingest_document
        ingest_document(db=db, document_id=doc_uuid, file_data=file_data, file_type=file_type)
        log.info("worker_ingestion_finished_successfully", document_id=document_id)
    except Exception as exc:
        log.exception("worker_ingestion_error", document_id=document_id, error=str(exc))
        _mark_doc_failed(doc_uuid, str(exc))
    finally:
        try:
            db.close()
        except Exception:
            pass
