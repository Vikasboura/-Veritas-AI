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


def get_sync_db():
    """Create a synchronous SQLAlchemy session for the worker process."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.DATABASE_SYNC_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def run_ingestion(document_id: str, file_data: bytes, file_type: str) -> None:
    """
    RQ job: ingest a single document.
    Args are primitive types (serializable by RQ/Redis).
    """
    configure_logging()
    doc_uuid = uuid.UUID(document_id)
    log.info("worker_ingestion_start", document_id=document_id, file_type=file_type)

    db = get_sync_db()
    try:
        from app.services.ingestion_service import ingest_document
        ingest_document(db=db, document_id=doc_uuid, file_data=file_data, file_type=file_type)
    finally:
        db.close()
