"""
app/api/v1/documents.py
────────────────────────
Document upload (multipart), list, delete, and status endpoints.
Routes are thin — all logic in document_service.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.api.deps import CurrentUser, DbSession, WorkspaceMemberDep, WorkspaceOwnerDep
from app.core.config import get_settings
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.services import document_service

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])
settings = get_settings()


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    db: DbSession = ...,
    current_user: CurrentUser = ...,
    _member: WorkspaceMemberDep = ...,
) -> DocumentUploadResponse:
    """
    Upload a document for ingestion.
    Returns 202 immediately; ingestion runs in background.
    """
    file_data = await file.read()

    try:
        doc, is_new = await document_service.upload_document(
            db=db,
            workspace_id=workspace_id,
            uploader_id=current_user.id,
            filename=file.filename or "upload",
            content_type=file.content_type,
            file_data=file_data,
        )
    except document_service.DocumentTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except document_service.UnsupportedFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))

    if not is_new:
        return DocumentUploadResponse(
            id=doc.id,
            filename=doc.filename,
            status=doc.status,
            message="Identical file already ingested. No re-processing needed.",
        )

    # Enqueue background ingestion job
    try:
        document_service.enqueue_ingestion(doc.id, file_data, doc.file_type)
    except Exception as exc:
        # If Redis is down, mark as failed so the user knows
        import asyncio
        from sqlalchemy import update
        from app.models.document import Document
        await db.execute(
            update(Document)
            .where(Document.id == doc.id)
            .values(status="failed", error_message=f"Queue unavailable: {exc}")
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion queue unavailable. Please try again later.",
        )

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        status="pending",
        message="Document accepted. Ingestion running in background.",
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: uuid.UUID,
    db: DbSession,
    _member: WorkspaceMemberDep,
) -> list[DocumentResponse]:
    docs = await document_service.list_documents(db, workspace_id)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    _member: WorkspaceMemberDep,
) -> DocumentResponse:
    try:
        doc = await document_service.get_document_or_404(db, workspace_id, document_id)
    except document_service.DocumentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    _owner: WorkspaceOwnerDep,
) -> None:
    try:
        await document_service.delete_document(db, workspace_id, document_id)
    except document_service.DocumentError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
